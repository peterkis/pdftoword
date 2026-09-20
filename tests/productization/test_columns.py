"""Real DAG, public structure and native Word section contracts for bounded columns."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn
from prototypes.docx_output.common import Json, new_job, relation
from prototypes.docx_output.planning.columns import select_columns, verify_selected_order
from prototypes.docx_output.planning.flow import plan_flow
from prototypes.docx_output.planning.reading_order import resolve_order
from prototypes.docx_output.renderers.flow import FlowRenderer
from prototypes.docx_output.structure_processors.bridge import json_hash
from prototypes.docx_output.structure_processors.docvortex import DocVortexStructureProcessor
from tests.productization.test_native_reflow import case, native_lines

__all__ = ["case"]


def column_ir(root: Path, mode: str = "plain", provider: str = "native_pdf") -> Json:
    """Deliberately row-major source observations, with unequal, measured column widths."""
    rows: list[tuple[str, list[float]]] = [
        ("Left one", [40, 100, 240, 130]),
        ("Right one", [280, 100, 550, 130]),
        ("Left two", [40, 150, 240, 180]),
        ("Right two", [280, 150, 550, 180]),
    ]
    if mode != "plain":
        rows.insert(0, ("Spanning heading", [40, 40, 550, 65]))
    if mode == "span":
        rows.extend(
            [
                ("Spanning caption", [40, 220, 550, 245]),
                ("Left three", [40, 280, 240, 310]),
                ("Right three", [280, 280, 550, 310]),
            ]
        )
    ir = native_lines(root, rows)
    for b in ir["pages"][0]["blocks"]:
        b["geometry_source"] = provider
    if mode != "plain":
        ir["pages"][0]["blocks"][0]["type"] = "heading"
    if mode == "span":
        ir["pages"][0]["blocks"][5]["type"] = "caption"
    return ir


@pytest.mark.parametrize("provider", ["native_pdf", "pp_structure"])
@pytest.mark.parametrize("mode", ["plain", "heading", "span"])
def test_columns_dag_and_actual_public_order(case: Path, provider: str, mode: str) -> None:
    ir = column_ir(case, mode, provider)
    original = copy.deepcopy(ir)
    selected = select_columns(ir)
    report = selected["metadata"]["column_layout"]["0"]
    assert report["status"] == "APPLIED" and ir == original
    ids = selected["pages"][0]["reading_order"]
    offset = 0 if mode == "plain" else 1
    assert ids.index(f"atom-{offset + 2}") < ids.index(f"atom-{offset + 1}")
    assert report["engine_confidence"] is None
    processor = DocVortexStructureProcessor()
    candidate = processor.process(selected)
    verify_selected_order(selected, candidate.document)
    assert [
        entry["source_id"] for entry in processor.last_execution["source_ledger"]["entries"]
    ] == ids
    p = plan_flow(candidate.document, families={"Arial", "Arial Unicode MS"})
    job = new_job(case / "output")
    FlowRenderer().render(job, p, "auto")
    doc = Document(str(job / "auto.docx"))
    cols = [s._sectPr.find(qn("w:cols")) for s in doc.sections]
    assert any(c is not None and c.get(qn("w:num")) == "2" for c in cols)
    assert doc.element.body.xpath('.//w:br[@w:type="column"]')
    assert not doc.tables
    if mode != "plain":
        assert any(s.start_type == 0 for s in doc.sections[1:])


def test_cycle_never_becomes_a_partial_order() -> None:
    p = resolve_order(["a", "b", "c"], [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}])
    assert p["status"] == "ABSTAIN" and p["order"] == ["a", "b", "c"]
    assert resolve_order(["a"], [{"from": "a", "to": "missing"}])["status"] == "ABSTAIN"


@pytest.mark.parametrize("mode", ["missing", "consistent", "conflict", "stale"])
def test_bound_provider_order_is_constraint_not_confidence(case: Path, mode: str) -> None:
    ir = column_ir(case)
    page = ir["pages"][0]
    ids = ["atom-0", "atom-2", "atom-1", "atom-3"]
    if mode == "conflict":
        ids = page["reading_order"]
    evidence = {
        "provider": "monkeyocrv2",
        "source_ids": ids,
        "source_page_sha256": json_hash(page),
        "source_content_sha256": {b["id"]: json_hash(b["content"]) for b in page["blocks"]},
    }
    if mode == "stale":
        evidence["source_page_sha256"] = "0" * 64
    if mode != "missing":
        ir["metadata"]["reading_order_evidence"] = {"0": [evidence]}
    result = select_columns(ir)
    report = result["metadata"]["column_layout"]["0"]
    assert report["status"] == ("ABSTAIN" if mode == "conflict" else "APPLIED")
    if mode == "conflict":
        assert report["reason"] == "ORDER_DAG_CYCLE"
    if mode == "stale":
        assert report["provider_constraints"][0]["status"] == "REJECTED"
    assert report["engine_confidence"] is None


def test_footnote_band_and_caption_relation(case: Path) -> None:
    ir = column_ir(case, "span")
    ir["pages"][0]["blocks"][5]["type"] = "footer"
    result = select_columns(ir)
    r = result["metadata"]["column_layout"]["0"]
    assert r["status"] == "APPLIED" and r["bands"][2]["spanning"]
    relation(ir, "precedes", "atom-2", "atom-1", {"manual": True})
    result = select_columns(ir)
    assert result["metadata"]["column_layout"]["0"]["status"] == "ABSTAIN"
    assert result["pages"][0]["reading_order"] == ir["pages"][0]["reading_order"]


def test_manual_and_stale_proof_fallback(case: Path) -> None:
    ir = column_ir(case)
    ir["pages"][0]["blocks"][0]["flags"].append("manual_lock")
    assert select_columns(ir)["metadata"]["column_layout"]["0"]["reason"] == "COLUMN_MANUAL_LOCK"
    ir["pages"][0]["blocks"][0]["flags"] = []
    result = select_columns(ir)
    result["pages"][0]["blocks"][0]["content"]["plain_text"] = "edited"
    p = plan_flow(result, families=set())
    assert any(i["code"] == "COLUMN_PROOF_STALE_SINGLE_COLUMN" for i in p.output_layout["issues"])
    assert all(len(s.get("column_widths_pt", [1])) == 1 for s in p.output_layout["sections"])


def test_noncontiguous_pages_keep_physical_boundary(case: Path) -> None:
    ir = column_ir(case)
    other = copy.deepcopy(ir["pages"][0])
    other["page_index"] = 3
    for b in other["blocks"]:
        b.update(id=b["id"] + "-p3", page_index=3)
    other["reading_order"] = [bid + "-p3" for bid in other["reading_order"]]
    ir["pages"].append(other)
    ir["source"]["page_count"] = 4
    p = plan_flow(select_columns(ir), families=set())
    assert [s["source_pages"] for s in p.output_layout["sections"]] == [[0], [3]]
    assert p.output_layout["sections"][1]["break_type"] == "next_page"


def test_multicolumn_table_is_explicit_local_fallback(case: Path) -> None:
    ir = column_ir(case, "span")
    ir["pages"][0]["blocks"][1]["type"] = "table"
    result = select_columns(ir)
    r = result["metadata"]["column_layout"]["0"]
    assert r["status"] == "APPLIED"  # Lower independently proved band remains usable.
    assert r["bands"][1]["reason"] == "COLUMN_TABLE_SCOPE_UNSUPPORTED"
    assert any(i["type"] == "COLUMN_LAYOUT_FALLBACK" for i in result["issues"])
    assert result["pages"][0]["blocks"] == ir["pages"][0]["blocks"]


def test_invalid_render_column_width_is_rejected(case: Path) -> None:
    from prototypes.docx_output.common import DemoError

    p = plan_flow(select_columns(column_ir(case)), families=set())
    p.output_layout["sections"][0]["column_widths_pt"][0] += 100
    with pytest.raises(DemoError, match="COLUMN_SECTION_WIDTH_INVALID"):
        p.as_dict()


def test_sealed_column_replay_preserves_source_and_ranges(case: Path) -> None:
    import shutil

    from prototypes.docx_output.acceptance import package_inventory
    from prototypes.docx_output.columns_replay import export_columns
    from prototypes.docx_output.common import DemoError, save
    from prototypes.docx_output.pipeline import finish
    from prototypes.docx_output.render_replay import inventory

    ir = column_ir(case)
    source = new_job(case / "baseline")
    shutil.copyfile(next(case.rglob("source-0.png")), source / "assets/source-0.png")
    finish(source, ir)
    before = inventory(source)
    seal = case / "seal.json"
    save(seal, {"source_files": before})
    job = export_columns(source, seal, case / "columns")
    assert inventory(source) == before
    assert package_inventory(job)["source_payloads_verified"]
    with pytest.raises(DemoError, match="OUTPUT_INSIDE_SOURCE"):
        export_columns(source, seal, source / "bad")


def test_spanning_pdf_figure_caption_stays_in_one_full_width_section(case: Path) -> None:
    import shutil

    from prototypes.docx_output.acceptance import package_inventory
    from prototypes.docx_output.common import block, crop, save
    from prototypes.docx_output.structure import image_content

    ir = column_ir(case, "span")
    base = new_job(case / "figure-source")
    shutil.copyfile(next(case.rglob("source-0.png")), base / "assets/source-0.png")
    page = ir["pages"][0]
    fig = page["blocks"][5]
    aid = crop(base, ir, page, fig["bbox"], "test-wide")
    fig.update(
        type="figure",
        geometry_source="pdf_image",
        source_type="pdf_image",
        content=image_content(aid),
        content_candidates=[],
        selected_candidate_id=None,
        render_policy="preserve_image",
    )
    cap = block("caption", 0, [40, 250, 550, 270], "Confirmed caption", "native_pdf", "caption")
    page["blocks"].append(cap)
    page["reading_order"].insert(6, "caption")
    relation(ir, "caption_of", "caption", fig["id"], {"manual": True})
    selected = select_columns(ir)
    plan = plan_flow(selected, families=set())
    sections = [
        s
        for s in plan.output_layout["sections"]
        if any(fig["id"] in n["source_ids"] for n in s["nodes"])
    ]
    assert len(sections) == 1
    assert sections[0]["column_widths_pt"] == [510]
    assert [n["source_ids"] for n in sections[0]["nodes"]] == [[fig["id"]], ["caption"]]
    assert sections[0]["nodes"][0]["keep_with_next"]
    out = new_job(case / "figure-output")
    shutil.copytree(base / "assets", out / "assets", dirs_exist_ok=True)
    FlowRenderer().render(out, plan, "auto")
    save(out / "layout.auto.json", plan.document)
    assert package_inventory(out)["source_payloads_verified"]


def test_cli_invalid_ir_does_not_log_source_text(case: Path) -> None:
    import shutil
    import subprocess

    from prototypes.docx_output.common import save
    from prototypes.docx_output.render_replay import inventory

    ir = column_ir(case)
    source = new_job(case / "invalid-source")
    shutil.copyfile(next(case.rglob("source-0.png")), source / "assets/source-0.png")
    ir["pages"][0]["blocks"][0]["type"] = "not-a-valid-type"
    ir["pages"][0]["blocks"][0]["content"]["plain_text"] = "DO_NOT_LOG_PRIVATE_SOURCE"
    save(source / "layout.auto.json", ir)
    seal = case / "bad-seal.json"
    save(seal, {"source_files": inventory(source)})
    p = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "prototypes.docx_output.columns_replay",
            "--source-job",
            str(source),
            "--source-seal",
            str(seal),
            "--output-root",
            str(case / "bad-output"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode == 1
    assert p.stderr.strip() == "COLUMN_REPLAY_FAILED_VALIDATIONERROR"
    assert "DO_NOT_LOG_PRIVATE_SOURCE" not in p.stdout + p.stderr
