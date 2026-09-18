"""Real public renderer, registered assets, content range mapping and explicit fallback."""

from __future__ import annotations

import copy
import shutil
import uuid
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from docx import Document
from lxml import etree
from prototypes.docx_output.common import PRIVATE, DemoError, digest, new_job, read, save
from prototypes.docx_output.docvortex_runtime import call_worker
from prototypes.docx_output.planning.render_plan import RenderPlan
from prototypes.docx_output.render_replay import compare_renderers, inventory
from prototypes.docx_output.renderers.docvortex import DocVortexRenderer
from prototypes.docx_output.structure_processors.bridge import bridge, direct_middle
from tests.productization.test_renderer_boundary import source_job


@pytest.fixture
def case() -> Iterator[Path]:
    """Use real private files and isolated worker, never mock the public renderer."""
    root = PRIVATE / ("docvortex-render-test-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root)


def test_real_renderer_same_plan_and_source_ranges(case: Path) -> None:
    source, ir = source_job(case)
    before = inventory(source)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    outputs = read(comparison / "comparison.json")["outputs"]
    a, b = [case / "jobs" / row["job_id"] for row in outputs]
    assert digest(a / "render-plan.auto.json") == digest(b / "render-plan.auto.json")
    audit = read(b / "docvortex-render-audit.auto.json")
    assert audit["public_call"] == "COMPLETE" and not audit["fallback"]
    assert not audit["worker"]["pdfium_loaded"]
    mapping = read(b / "source-map.auto.json")
    assert mapping["schema_version"] == "docx-source-map/1.0"
    assert mapping["docx_sha256"] == digest(b / "auto.docx")
    assert [x["block_id"] for x in mapping["blocks"]] == ["question", "figure"]
    with zipfile.ZipFile(b / "auto.docx") as package:
        tree = etree.fromstring(package.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        starts = tree.xpath('//w:bookmarkStart[starts-with(@w:name,"p2w_")]', namespaces=ns)
        assert len(starts) == 2
        assert starts[0].getnext().tag.endswith("}r")
    assert Document(str(b / "auto.docx")).styles["Normal"].font.size.pt == 11
    assert inventory(source) == before
    assert read(b / "layout.auto.json")["pages"] == ir["pages"]


def test_unsupported_geometry_falls_back_without_losing_content(case: Path) -> None:
    source, ir = source_job(case)
    ir["metadata"]["layout_profile"] = "pp_geometry_flow"
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    b = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(b / "docvortex-render-audit.auto.json")
    assert audit["fallback"] and audit["public_call"] == "NOT_RUN"
    assert read(b / "qa.json")["effective_renderer"] == "legacy"
    assert Document(str(b / "auto.docx")).paragraphs[0].text == "1. Keep < exact > content"


@pytest.mark.parametrize("fault", ["missing", "changed", "remote", "traversal"])
def test_worker_asset_resolver_rejects_unregistered_inputs(case: Path, fault: str) -> None:
    source, ir = source_job(case)
    value = bridge(ir, for_renderer=True)
    middle = direct_middle(value)
    asset = ir["assets"][0]
    registry = {asset["path"]: asset["sha256"]}
    if fault == "missing":
        registry.clear()
    elif fault == "changed":
        registry[asset["path"]] = "0" * 64
    else:
        body = middle["pages"][0]["blocks"][1]["content"][0]
        if fault == "remote":
            body["image_url"] = "https://example.invalid/no-network.png"
        else:
            body["image_path"] = "../outside.png"
    with pytest.raises(DemoError, match="DOCVORTEX_PUBLIC_CALL_FAILED"):
        call_worker(
            {
                "action": "render",
                "middle": middle,
                "assets": registry,
                "job": str(source),
                "output": str(case / "forbidden.docx"),
            }
        )
    assert not (case / "forbidden.docx").exists()


def test_auxiliary_text_is_preserved_by_adapter(case: Path) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][0]["type"] = "footer"
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    b = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    assert not read(b / "docvortex-render-audit.auto.json")["fallback"]
    assert Document(str(b / "auto.docx")).paragraphs[0].text == "1. Keep < exact > content"


def test_formula_image_fallback_and_raw_latex_rejection(case: Path) -> None:
    source, ir = source_job(case)
    b = ir["pages"][0]["blocks"][1]
    b["type"] = "formula"
    b["content"] = {
        "kind": "formula",
        "latex": r"\frac{",
        "mathml": None,
        "source_asset_id": ir["assets"][0]["id"],
        "render_mode": "omml_with_image_fallback",
        "confidence": 0,
        "omml_status": "pending",
    }
    target = new_job(case / "jobs")
    for asset in ir["assets"]:
        dest = target / asset["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / asset["path"], dest)
    stats = DocVortexRenderer().render(target, RenderPlan.from_ir(ir), "auto")
    assert stats["formula_image_count"] == 1 and stats["omml_formula_count"] == 0
    assert (
        read(target / "docvortex-render-audit.auto.json")["losses"][0]["code"]
        == "FORMULA_IMAGE_FALLBACK"
    )
    ir2 = copy.deepcopy(ir)
    ir2["pages"][0]["blocks"][1]["content"]["source_asset_id"] = "unavailable"
    target2 = new_job(case / "jobs")
    for asset in ir2["assets"]:
        dest = target2 / asset["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / asset["path"], dest)
    with pytest.raises(DemoError):
        DocVortexRenderer().render(target2, RenderPlan.from_ir(ir2), "auto")
    assert not (target2 / "auto.docx").exists()


def test_integrity_failure_never_downgrades_to_legacy(case: Path) -> None:
    source, ir = source_job(case)
    target = new_job(case / "jobs")
    for asset in ir["assets"]:
        dest = target / asset["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / asset["path"], dest)
    ir["assets"][0]["sha256"] = "0" * 64
    with pytest.raises(DemoError, match="ASSET_HASH"):
        DocVortexRenderer().render(target, RenderPlan.from_ir(ir), "auto")
    assert not (target / "auto.docx").exists()


def test_poc_cannot_allocate_inside_original_job(case: Path) -> None:
    from prototypes.docx_output.reuse_poc import run_poc

    source, _ = source_job(case)
    before = inventory(source)
    with pytest.raises(DemoError, match="OUTPUT_INSIDE_SOURCE"):
        run_poc(source, output_root=source / "nested")
    assert inventory(source) == before


def test_inline_formula_is_written_as_actual_omml(case: Path) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][0]["content"]["plain_text"] = "Value x^2"
    ir["metadata"]["structure_evidence"] = {
        "question": {
            "inline_spans": [
                {"type": "text", "content": "Value "},
                {"type": "equation_inline", "content": "x^2"},
            ]
        }
    }
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    b = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(b / "docvortex-render-audit.auto.json")
    assert audit["public_call"] == "COMPLETE" and not audit["fallback"]
    assert read(b / "qa.json")["omml_formula_count"] == 1


@pytest.mark.parametrize("source_kind", ["data", "remote"])
def test_table_html_cannot_bypass_local_asset_registry(case: Path, source_kind: str) -> None:
    import base64

    source, ir = source_job(case)
    middle = direct_middle(bridge(ir, for_renderer=True))
    asset = ir["assets"][0]
    url = "https://example.invalid/unregistered.png"
    if source_kind == "data":
        encoded = base64.b64encode((source / asset["path"]).read_bytes()).decode()
        url = "data:image/png;base64," + encoded
    image = middle["pages"][0]["blocks"][1]
    image["type"] = "table"
    image["content"][0] = {
        "type": "table_body",
        "index": image["index"],
        "bbox": image["bbox"],
        "content": f'<table><tr><td><img src="{url}"/></td></tr></table>',
    }
    with pytest.raises(DemoError, match="DOCVORTEX_PUBLIC_CALL_FAILED"):
        call_worker(
            {
                "action": "render",
                "middle": middle,
                "assets": {asset["path"]: asset["sha256"]},
                "job": str(source),
                "output": str(case / "forbidden.docx"),
            }
        )
    assert not (case / "forbidden.docx").exists()


def test_editable_table_has_one_verified_source_range(case: Path) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][0]["type"] = "table"
    ir["pages"][0]["blocks"][0]["content"]["plain_text"] = "ABC"
    ir["metadata"]["structure_evidence"] = {
        "question": {
            "selected_html": (
                '<table><tr><td rowspan="2">A</td><td>B</td></tr>'
                '<tr><td>C</td></tr></table>'
            )
        }
    }
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    b = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    assert not read(b / "docvortex-render-audit.auto.json")["fallback"]
    assert len(Document(str(b / "auto.docx")).tables) == 1
    mapping = read(b / "source-map.auto.json")
    assert mapping["blocks"][0]["kind"] == "table"
    with zipfile.ZipFile(b / "auto.docx") as package:
        xml = etree.fromstring(package.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        marker = xml.xpath(
            "//w:bookmarkStart[@w:name=$name]", namespaces=ns, name=mapping["blocks"][0]["marker"]
        )[0]
        assert marker.getnext().tag.endswith("}tbl")
        assert marker.getnext().getnext().tag.endswith("}bookmarkEnd")
