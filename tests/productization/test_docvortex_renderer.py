"""Real public renderer, registered assets, content range mapping and explicit fallback."""

from __future__ import annotations

import copy
import shutil
import uuid
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

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
    b["render_policy"] = "hybrid"
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


def test_table_width_limit_keeps_raw_candidate_and_explicit_rejection(case: Path) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][0]["type"] = "table"
    ir["pages"][0]["blocks"][0]["content"]["plain_text"] = "ABC"
    ir["metadata"]["structure_evidence"] = {
        "question": {
            "selected_html": (
                '<table><tr><td rowspan="2">A</td><td>B</td></tr><tr><td>C</td></tr></table>'
            )
        }
    }
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    b = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(b / "docvortex-render-audit.auto.json")
    assert audit["fallback"] and audit["public_call"] == "COMPLETE"
    assert any(
        loss["code"] == "DOCVORTEX_VISIBILITY_UNSUPPORTED:UNSUPPORTED_TABLE_WIDTH"
        for loss in audit["losses"]
    )
    assert len(Document(str(b / audit["raw_docx"])).tables) == 1
    assert Document(str(b / "auto.docx")).paragraphs[0].text == "ABC"
    assert read(b / "render-manifest.auto.json")["effective_renderer"] == "legacy"


def test_deduplicated_image_paths_keep_distinct_source_boxes(case: Path) -> None:
    source, ir = source_job(case)
    first = ir["assets"][0]
    duplicate = copy.deepcopy(first)
    duplicate.update(id="second-asset", source_bbox=[110, 150, 200, 200])
    ir["assets"].append(duplicate)
    second = copy.deepcopy(ir["pages"][0]["blocks"][1])
    second["id"] = "second-figure"
    second["bbox"] = duplicate["source_bbox"]
    second["content"]["asset_id"] = duplicate["id"]
    ir["pages"][0]["blocks"].append(second)
    ir["pages"][0]["reading_order"].append(second["id"])
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    records = read(target / "source-map.auto.json")["blocks"]
    assert records[2]["images"][0]["bbox"] == duplicate["source_bbox"]
    assert records[1]["images"][0]["bbox"] == first["source_bbox"]


def test_ordinary_html_table_with_void_tag_and_entity(case: Path) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][0]["type"] = "table"
    ir["pages"][0]["blocks"][0]["content"]["plain_text"] = "A\nB\u00a0C"
    ir["metadata"]["structure_evidence"] = {
        "question": {"selected_html": "<table><tr><td>A<br>B&nbsp;C</td></tr></table>"}
    }
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"] and audit["public_call"] == "COMPLETE"
    assert Document(str(target / audit["raw_docx"])).tables[0].cell(0, 0).text == "A\nB\u00a0C"
    assert Document(str(target / "auto.docx")).paragraphs[0].text == "A\nB\u00a0C"


@pytest.mark.parametrize("change", ["boundaries", "merge"])
def test_table_topology_change_rejected_before_source_binding(case: Path, change: str) -> None:
    from prototypes.docx_output.renderers.docvortex import bind_source_ranges

    _, ir = source_job(case)
    doc = Document()
    table = doc.add_table(rows=1, cols=2)
    if change == "boundaries":
        table.cell(0, 0).text, table.cell(0, 1).text = "AB", "C"
    else:
        table.cell(0, 0).merge(table.cell(0, 1)).text = "ABC"
    raw = case / "altered-table.docx"
    doc.save(str(raw))
    entry = {
        "block": ir["pages"][0]["blocks"][0],
        "raw": {"type": "table", "content": "<table><tr><td>A</td><td>BC</td></tr></table>"},
    }
    with pytest.raises(DemoError, match="DOCVORTEX_TABLE_TOPOLOGY"):
        bind_source_ranges(raw, case / "rejected.docx", ir, [entry])
    assert not (case / "rejected.docx").exists()


@pytest.mark.parametrize("inline", [False, True])
def test_changed_formula_rejected_before_source_binding(case: Path, inline: bool) -> None:
    from prototypes.docx_output.formula import to_omml
    from prototypes.docx_output.renderers.docvortex import bind_source_ranges

    _, ir = source_job(case)
    doc = Document()
    paragraph: Any = doc.add_paragraph()._p
    paragraph.append(etree.fromstring(to_omml("x^3").encode()))
    raw = case / "altered-formula.docx"
    doc.save(str(raw))
    source = (
        {"type": "text", "content": [{"type": "equation_inline", "content": "x^2"}]}
        if inline
        else {"type": "equation", "content": "x^2"}
    )
    with pytest.raises(DemoError, match="DOCVORTEX_FORMULA_UNVERIFIED"):
        bind_source_ranges(
            raw, case / "rejected.docx", ir, [{"block": ir["pages"][0]["blocks"][0], "raw": source}]
        )
    assert not (case / "rejected.docx").exists()


@pytest.mark.parametrize("markup", [None, "", "   "])
def test_table_without_structure_evidence_falls_back(case: Path, markup: str | None) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][0]["type"] = "table"
    ir["metadata"]["structure_evidence"] = {"question": {"selected_html": markup}}
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"]
    assert any(loss["code"] == "TABLE_STRUCTURE_EVIDENCE_MISSING" for loss in audit["losses"])


def test_heading_preserves_planned_outline_level(case: Path) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][0]["type"] = "heading"
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"] and audit["public_call"] == "NOT_RUN"
    assert any(loss["code"] == "PLANNED_HEADING_LEVEL_UNSUPPORTED" for loss in audit["losses"])
    style = Document(str(target / "auto.docx")).paragraphs[0].style
    assert style is not None and style.name == "Heading 1"


@pytest.mark.parametrize("kind", ["caption", "footer"])
def test_caption_style_preserved_in_actual_output(case: Path, kind: str) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][0]["type"] = kind
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    assert not read(target / "docvortex-render-audit.auto.json")["fallback"]
    paragraph = Document(str(target / "auto.docx")).paragraphs[0]
    assert paragraph.style is not None and paragraph.style.name == "Caption"
    assert paragraph.text == ir["pages"][0]["blocks"][0]["content"]["plain_text"]


def test_inline_formula_reordering_is_rejected(case: Path) -> None:
    from prototypes.docx_output.formula import to_omml
    from prototypes.docx_output.renderers.docvortex import bind_source_ranges

    _, ir = source_job(case)
    doc = Document()
    paragraph: Any = doc.add_paragraph("AB")._p
    paragraph.append(etree.fromstring(to_omml("x").encode()))
    raw = case / "reordered.docx"
    doc.save(str(raw))
    spans = [
        {"type": "text", "content": "A"},
        {"type": "equation_inline", "content": "x"},
        {"type": "text", "content": "B"},
    ]
    with pytest.raises(DemoError, match="DOCVORTEX_INLINE_ORDER_CHANGED"):
        bind_source_ranges(
            raw,
            case / "rejected.docx",
            ir,
            [{"block": ir["pages"][0]["blocks"][0], "raw": {"type": "text", "content": spans}}],
        )


def test_text_backed_formula_explicitly_falls_back(case: Path) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][0]["type"] = "formula"
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"]
    assert any(loss["code"] == "FORMULA_STRUCTURE_EVIDENCE_MISSING" for loss in audit["losses"])


def test_poc_rejects_renderer_axis_fallback(case: Path) -> None:
    from prototypes.docx_output.reuse_poc import run_poc

    source, ir = source_job(case)
    ir["pages"][0]["blocks"][0]["type"] = "heading"
    save(source / "layout.auto.json", ir)
    before = inventory(source)
    with pytest.raises(DemoError, match="POC_RENDERER_AXIS_FALLBACK"):
        run_poc(source, output_root=case / "poc")
    rejection = next((case / "poc").rglob("renderer-axis-rejection.json"))
    assert read(rejection)["effective_renderer"] == "legacy"
    assert read(rejection)["status"] == "INVALID_FALLBACK"
    assert not list((case / "poc").rglob("poc-manifest.json"))
    assert inventory(source) == before


def test_render_audit_fingerprints_local_execution_dependencies(case: Path) -> None:
    from prototypes.docx_output.common import ROOT

    source, _ = source_job(case)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(target / "docvortex-render-audit.auto.json")
    for name in [
        "structure_processors/bridge.py",
        "renderers/verification.py",
        "docvortex_runtime.py",
        "docvortex_worker.py",
    ]:
        expected = digest(ROOT / "prototypes/docx_output" / name)
        assert audit["local_implementation_sha256"][name] == expected
        assert audit["worker"]["local_implementation_sha256"][name] == expected
    assert all(not Path(name).is_absolute() for name in audit["local_implementation_sha256"])


@pytest.mark.parametrize(
    "kind",
    [
        "list",
        "list_item",
        "section",
        "table_row",
        "table_cell",
        "header",
        "answer_area",
        "layout_container",
        "unknown",
    ],
)
def test_unsupported_block_semantics_are_not_silently_flattened(case: Path, kind: str) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][0]["type"] = kind
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"] and audit["public_call"] == "NOT_RUN"
    assert any(
        loss["code"] == "BLOCK_TYPE_UNSUPPORTED" and loss["block_type"] == kind
        for loss in audit["losses"]
    )


@pytest.mark.parametrize("cropped", [False, True])
def test_image_visibility_and_source_dimensions(case: Path, cropped: bool) -> None:
    from docx.oxml import OxmlElement
    from docx.shared import Pt
    from prototypes.docx_output.renderers.docvortex import bind_source_ranges

    source, ir = source_job(case)
    asset = ir["assets"][0]
    doc = Document()
    shape = doc.add_picture(str(source / asset["path"]), width=Pt(1), height=Pt(1))
    if cropped:
        crop = OxmlElement("a:srcRect")
        crop.set("l", "50000")
        shape._inline.xpath(".//pic:blipFill")[0].append(crop)
    raw, target = case / "raw-image.docx", case / "bound-image.docx"
    doc.save(str(raw))
    entry = {
        "block": ir["pages"][0]["blocks"][1],
        "raw": {"type": "image", "content": "", "image_path": asset["path"]},
    }
    if cropped:
        with pytest.raises(DemoError, match="DOCVORTEX_IMAGE_GEOMETRY_UNSUPPORTED"):
            bind_source_ranges(raw, target, ir, [entry])
        assert not target.exists()
    else:
        bind_source_ranges(raw, target, ir, [entry])
        output = Document(str(target)).inline_shapes[0]
        from PIL import Image

        with Image.open(source / asset["path"]) as original:
            width, height = original.size
        assert output.width == Pt(90)
        assert abs(output.height / output.width - height / width) < 0.00001


def test_table_header_semantics_explicitly_unsupported(case: Path) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][0]["type"] = "table"
    ir["pages"][0]["blocks"][0]["content"]["plain_text"] = "A"
    ir["metadata"]["structure_evidence"] = {
        "question": {"selected_html": "<table><thead><tr><th>A</th></tr></thead></table>"}
    }
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"]
    assert any(loss["code"] == "DOCVORTEX_TABLE_HEADER_UNSUPPORTED" for loss in audit["losses"])


@pytest.mark.parametrize(
    "policy,mode", [("editable", "image"), ("preserve_image", "omml_with_image_fallback")]
)
def test_explicit_formula_image_policy_is_not_overridden(
    case: Path, policy: str, mode: str
) -> None:
    source, ir = source_job(case)
    b = ir["pages"][0]["blocks"][1]
    b.update(type="formula", render_policy=policy)
    b["content"] = {
        "kind": "formula",
        "latex": "x^2",
        "mathml": None,
        "source_asset_id": ir["assets"][0]["id"],
        "render_mode": mode,
        "confidence": 0,
        "omml_status": "pending",
    }
    target = new_job(case / "jobs")
    for asset in ir["assets"]:
        destination = target / asset["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / asset["path"], destination)
    # Neither adapter can render this unprepared formula content: preserve explicit failure.
    with pytest.raises(DemoError, match="UNSUPPORTED_IR_CONTENT"):
        DocVortexRenderer().render(target, RenderPlan.from_ir(ir), "auto")
    assert not (target / "auto.docx").exists()
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"] and audit["public_call"] == "NOT_RUN"
    assert any(loss["code"] == "FORMULA_IMAGE_POLICY_UNSUPPORTED" for loss in audit["losses"])


@pytest.mark.parametrize("mode", ["editable_text", "metadata_only"])
def test_nonvisual_image_mode_is_explicitly_unsupported(case: Path, mode: str) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][1]["content"]["render_mode"] = mode
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"] and audit["public_call"] == "NOT_RUN"
    assert any(loss["code"] == "IMAGE_RENDER_MODE_UNSUPPORTED" for loss in audit["losses"])


def test_source_style_reference_explicitly_unsupported(case: Path) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][0]["style_ref"] = "source-style"
    assert ir["styles"] == {}
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"] and audit["public_call"] == "NOT_RUN"
    assert any(loss["code"] == "BLOCK_SOURCE_STYLE_UNSUPPORTED" for loss in audit["losses"])


@pytest.mark.parametrize(
    "span",
    [
        {"type": "hyperlink", "content": "Link", "url": "https://example.invalid/"},
        {"type": "text", "content": "Link", "bold": True},
    ],
)
def test_unverified_inline_semantics_explicitly_unsupported(case: Path, span: dict) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][0]["content"]["plain_text"] = "Link"
    ir["metadata"]["structure_evidence"] = {"question": {"inline_spans": [span]}}
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"] and audit["public_call"] == "NOT_RUN"
    assert any(loss["code"] == "INLINE_SPAN_UNSUPPORTED" for loss in audit["losses"])


@pytest.mark.parametrize(
    "cell",
    [
        '<td><a href="https://example.invalid/">A</a></td>',
        "<td><strong>A</strong></td>",
        "<td><em>A</em></td>",
        '<td style="color:red">A</td>',
    ],
)
def test_rich_table_cell_markup_is_explicitly_unsupported(case: Path, cell: str) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][0]["type"] = "table"
    ir["pages"][0]["blocks"][0]["content"]["plain_text"] = "A"
    ir["metadata"]["structure_evidence"] = {
        "question": {"selected_html": "<table><tr>" + cell + "</tr></table>"}
    }
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"] and audit["public_call"] == "NOT_RUN"
    assert any(loss["code"] == "TABLE_RICH_CONTENT_UNSUPPORTED" for loss in audit["losses"])


def test_image_backed_formula_is_counted_as_formula_fallback(case: Path) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][1]["type"] = "formula"
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    assert not read(target / "docvortex-render-audit.auto.json")["fallback"]
    qa = read(target / "qa.json")
    assert qa["formula_image_count"] == 1
    assert qa["omml_formula_count"] == 0
    assert read(target / "source-map.auto.json")["blocks"][1]["formula_image"]


def test_omml_only_formula_never_accepts_raster_fallback(case: Path) -> None:
    source, ir = source_job(case)
    b = ir["pages"][0]["blocks"][1]
    b.update(type="formula", render_policy="editable")
    b["content"] = {
        "kind": "formula",
        "latex": r"\frac{",
        "mathml": None,
        "source_asset_id": ir["assets"][0]["id"],
        "render_mode": "omml",
        "confidence": 0,
        "omml_status": "pending",
    }
    value = bridge(ir, for_renderer=True)
    assert "image_path" not in value.ledger["entries"][1]["raw"]
    target = new_job(case / "jobs")
    for asset in ir["assets"]:
        destination = target / asset["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / asset["path"], destination)
    with pytest.raises(DemoError, match="UNSUPPORTED_IR_CONTENT"):
        DocVortexRenderer().render(target, RenderPlan.from_ir(ir), "auto")
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"]
    assert any(loss["code"] == "DOCVORTEX_OMML_ONLY_FORMULA_FAILED" for loss in audit["losses"])
    assert not (target / "auto.docx").exists()


def test_text_outside_table_cells_cannot_be_silently_lost(case: Path) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][0]["type"] = "table"
    ir["pages"][0]["blocks"][0]["content"]["plain_text"] = "AB"
    ir["metadata"]["structure_evidence"] = {
        "question": {"selected_html": "<table><tr><td>A</td></tr></table>B"}
    }
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"]
    assert any(loss["code"] == "DOCVORTEX_OUTPUT_CONTENT_CHANGED" for loss in audit["losses"])
    assert Document(str(target / "auto.docx")).paragraphs[0].text == "AB"


@pytest.mark.parametrize("kind", ["table", "paragraph"])
def test_formula_content_with_other_block_type_rejects(case: Path, kind: str) -> None:
    source, ir = source_job(case)
    b = ir["pages"][0]["blocks"][0]
    b["type"] = kind
    b["content"] = {
        "kind": "formula",
        "latex": "x^2",
        "mathml": None,
        "source_asset_id": ir["assets"][0]["id"],
        "render_mode": "omml",
        "confidence": 0,
        "omml_status": "pending",
    }
    target = new_job(case / "jobs")
    for asset in ir["assets"]:
        destination = target / asset["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / asset["path"], destination)
    with pytest.raises(DemoError, match="UNSUPPORTED_IR_CONTENT"):
        DocVortexRenderer().render(target, RenderPlan.from_ir(ir), "auto")
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"] and audit["public_call"] == "NOT_RUN"
    assert any(loss["code"] == "BLOCK_CONTENT_COMBINATION_UNSUPPORTED" for loss in audit["losses"])


@pytest.mark.parametrize("latex,editable", [("x^2", True), (r"\frac{", False)])
def test_formula_only_page_editability_matches_actual_output(
    case: Path, latex: str, editable: bool
) -> None:
    from prototypes.docx_output.pipeline import finish

    source, ir = source_job(case)
    b = ir["pages"][0]["blocks"][0]
    b.update(type="formula", render_policy="hybrid")
    b["content"] = {
        "kind": "formula",
        "latex": latex,
        "mathml": None,
        "source_asset_id": ir["assets"][0]["id"],
        "render_mode": "omml_with_image_fallback",
        "confidence": 0,
        "omml_status": "pending",
    }
    ir["pages"][0]["blocks"] = [b]
    ir["pages"][0]["reading_order"] = [b["id"]]
    ir["relations"] = []
    target = case / "formula-output"
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("*.docx"))
    qa = finish(target, ir, renderer=DocVortexRenderer())
    assert qa["page_editable_content"] == {"0": editable}
    assert qa["omml_formula_count"] == int(editable)
    assert qa["formula_image_count"] == int(not editable)
    assert qa["execution_status"] == ("COMPLETE" if editable else "DEMO_OUTPUT_INSUFFICIENT")


def test_image_alternative_text_is_explicitly_unsupported(case: Path) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][1]["content"]["alt_text"] = "Synthetic source description"
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"] and audit["public_call"] == "NOT_RUN"
    assert any(loss["code"] == "IMAGE_ALT_TEXT_UNSUPPORTED" for loss in audit["losses"])


@pytest.mark.parametrize(
    "placement", ["below_stem", "right_of_stem", "option_grid", "full_width", "local_group"]
)
def test_noninline_image_placement_explicitly_unsupported(case: Path, placement: str) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][1]["content"]["placement_hint"] = placement
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"] and audit["public_call"] == "NOT_RUN"
    assert any(loss["code"] == "IMAGE_PLACEMENT_UNSUPPORTED" for loss in audit["losses"])


@pytest.mark.parametrize("kind", ["major_question", "subquestion", "text_line", "text_span"])
def test_supported_main_text_page_is_editable(case: Path, kind: str) -> None:
    from prototypes.docx_output.pipeline import finish

    source, ir = source_job(case)
    b = ir["pages"][0]["blocks"][0]
    b["type"] = kind
    ir["pages"][0]["blocks"] = [b]
    ir["pages"][0]["reading_order"] = [b["id"]]
    ir["relations"] = []
    target = case / "main-text-output"
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("*.docx"))
    qa = finish(target, ir, renderer=DocVortexRenderer())
    assert qa["page_editable_content"] == {"0": True}
    assert qa["execution_status"] == "COMPLETE"


def test_formula_source_reference_must_resolve_even_for_valid_omml(case: Path) -> None:
    source, ir = source_job(case)
    b = ir["pages"][0]["blocks"][0]
    b.update(type="formula", render_policy="editable")
    b["content"] = {
        "kind": "formula",
        "latex": "x^2",
        "mathml": None,
        "source_asset_id": "missing",
        "render_mode": "omml",
        "confidence": 0,
        "omml_status": "pending",
    }
    target = new_job(case / "jobs")
    for asset in ir["assets"]:
        destination = target / asset["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / asset["path"], destination)
    with pytest.raises(DemoError):
        DocVortexRenderer().render(target, RenderPlan.from_ir(ir), "auto")
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"] and audit["public_call"] == "NOT_RUN"
    assert any(loss["code"] == "BRIDGE_FORMULA_ASSET_MISSING" for loss in audit["losses"])
    assert not (target / "auto.docx").exists()


@pytest.mark.parametrize("index", [0, 1])
def test_rotated_blocks_are_explicitly_unsupported(case: Path, index: int) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["blocks"][index]["rotation"] = 15
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"] and audit["public_call"] == "NOT_RUN"
    assert any(loss["code"] == "BLOCK_ROTATION_UNSUPPORTED" for loss in audit["losses"])


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_page_rotation_is_explicitly_unsupported(case: Path, rotation: int) -> None:
    source, ir = source_job(case)
    ir["pages"][0]["rotation"] = rotation
    save(source / "layout.auto.json", ir)
    comparison = compare_renderers(
        source, output_root=case / "jobs", renderer_b=DocVortexRenderer()
    )
    target = case / "jobs" / read(comparison / "comparison.json")["outputs"][1]["job_id"]
    audit = read(target / "docvortex-render-audit.auto.json")
    assert audit["fallback"] and audit["public_call"] == "NOT_RUN"
    assert any(loss["code"] == "PAGE_ROTATION_UNSUPPORTED" for loss in audit["losses"])


@pytest.mark.parametrize("mode", ["direct", "inherited", "white"])
def test_invisible_text_is_rejected_before_publishing(case: Path, mode: str) -> None:
    from docx.shared import RGBColor
    from prototypes.docx_output.renderers.docvortex import bind_source_ranges

    _, ir = source_job(case)
    b = ir["pages"][0]["blocks"][0]
    doc = Document()
    run = doc.add_paragraph().add_run(b["content"]["plain_text"])
    if mode == "direct":
        run.font.hidden = True
    elif mode == "inherited":
        doc.styles["Normal"].font.hidden = True
    else:
        run.font.color.rgb = RGBColor(255, 255, 255)
    raw, target = case / "hidden.docx", case / "rejected.docx"
    doc.save(str(raw))
    with pytest.raises(DemoError, match="DOCVORTEX_VISIBILITY_UNSUPPORTED"):
        bind_source_ranges(
            raw,
            target,
            ir,
            [{"block": b, "raw": {"type": "text", "content": b["content"]["plain_text"]}}],
        )
    assert not target.exists()


@pytest.mark.parametrize("tag", ["wp:docPr", "pic:cNvPr"])
def test_hidden_drawing_is_rejected_before_publication(case: Path, tag: str) -> None:
    from prototypes.docx_output.renderers.docvortex import bind_source_ranges

    source, ir = source_job(case)
    asset = ir["assets"][0]
    doc = Document()
    shape = doc.add_picture(str(source / asset["path"]))
    shape._inline.xpath(".//" + tag)[0].set("hidden", "1")
    raw, target = case / "hidden-image.docx", case / "rejected.docx"
    doc.save(str(raw))
    entry = {
        "block": ir["pages"][0]["blocks"][1],
        "raw": {"type": "image", "content": "", "image_path": asset["path"]},
    }
    with pytest.raises(DemoError, match="DOCVORTEX_VISIBILITY_UNSUPPORTED:HIDDEN_CONTENT"):
        bind_source_ranges(raw, target, ir, [entry])
    assert not target.exists()
