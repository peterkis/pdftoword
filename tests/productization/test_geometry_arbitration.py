"""Provider selection, abstention, and native precision without model calls."""

from __future__ import annotations

import copy

import pytest
from prototypes.docx_output.common import Json, block
from prototypes.docx_output.geometry.arbitrator import GeometryArbitrator, project_explicit_order
from prototypes.docx_output.geometry.candidate import TransformChain, record
from prototypes.docx_output.geometry.support import content_support
from prototypes.docx_output.structure_processors.bridge import json_hash


def fixture() -> tuple[Json, Json]:
    page: Json = {
        "page_index": 0,
        "width_pt": 100,
        "height_pt": 100,
        "blocks": [block("b0", 0, [0, 0, 100, 100], "source", "inferred")],
        "reading_order": ["b0"],
        "geometry_candidates": [],
    }
    support = {
        "b0": {
            "basis": "exact_pp_text",
            "bbox_pt": [10, 10, 40, 20],
            "source_content_sha256": json_hash(page["blocks"][0]["content"]),
        }
    }
    return page, support


def macro(provider: str, box: list[float], index: int = 0) -> Json:
    chain = TransformChain((100, 100), (100, 100), (0, 0, 100, 100), (100, 100))
    return record(
        provider, 0, index, "text", "region", "semantic_region", box, "input_pixel", chain, {}
    )


@pytest.mark.parametrize("winner", ["monkey", "pp"])
def test_provider_selected_and_geometry_changes(winner: str) -> None:
    page, support = fixture()
    other = "pp" if winner == "monkey" else "monkey"
    page["geometry_candidates"] = [macro(winner, [9, 9, 41, 21]), macro(other, [0, 0, 100, 100])]
    before = copy.deepcopy(page)
    projected, report = GeometryArbitrator().propose(page, support)
    assert report["selected_provider"] == winner
    assert projected["blocks"][0]["bbox"] == [9, 9, 41, 21]
    assert projected["blocks"][0]["selected_geometry_id"] == page["geometry_candidates"][0]["id"]
    assert projected["blocks"][0]["content"] == page["blocks"][0]["content"]
    assert page == before


@pytest.mark.parametrize(
    "fault", ["duplicate", "huge", "missing", "no_support", "stale", "caption", "frame", "tie"]
)
def test_unsafe_candidates_abstain(fault: str) -> None:
    page, support = fixture()
    candidate = macro("monkey", [9, 9, 41, 21])
    page["geometry_candidates"] = [candidate]
    if fault == "duplicate":
        page["geometry_candidates"].append(copy.deepcopy(candidate))
    elif fault == "huge":
        candidate["bbox_pt"] = [0, 0, 100, 100]
    elif fault == "missing":
        candidate["bbox_pt"] = [50, 50, 60, 60]
    elif fault == "no_support":
        support = {}
    elif fault == "stale":
        support["b0"]["source_content_sha256"] = "wrong"
    elif fault == "caption":
        candidate["label"] = "caption"
    elif fault == "frame":
        candidate["page_index"] = 2
    else:
        page["geometry_candidates"].append(macro("pp", [9, 9, 41, 21]))
    result, report = GeometryArbitrator().propose(page, support)
    assert report["status"] == "ABSTAIN" and result == page


def test_native_coordinates_not_overwritten_by_macro() -> None:
    page, support = fixture()
    page["blocks"][0]["geometry_source"] = "native_pdf"
    page["blocks"][0]["bbox"] = [10, 10, 40, 20]
    support["b0"]["basis"] = "native_verified_run"
    page["geometry_candidates"] = [macro("monkey", [9, 9, 41, 21])]
    projected, report = GeometryArbitrator().propose(page, support)
    assert report["status"] == "SELECTED"
    assert projected["blocks"][0]["bbox"] == page["blocks"][0]["bbox"]
    assert report["bindings"]["b0"]["native_measurement_preserved"]


def test_lines_never_compete_as_macro() -> None:
    page, support = fixture()
    candidate = macro("pp", [10, 10, 40, 20])
    candidate.update(hierarchy_level="line", granularity="ocr_line_box")
    page["geometry_candidates"] = [candidate]
    assert GeometryArbitrator().propose(page, support)[1]["status"] == "ABSTAIN"


def test_exact_alignment_preserves_output_and_rejects_same_text_at_two_locations() -> None:
    page, _ = fixture()
    chain = TransformChain((100, 100), (100, 100), (0, 0, 100, 100), (100, 100))
    pp: Json = {
        "result": {
            "layoutParsingResults": [
                {
                    "prunedResult": {
                        "width": 100,
                        "height": 100,
                        "model_settings": {"use_doc_preprocessor": False},
                        "overall_ocr_res": {
                            "rec_texts": ["source"],
                            "rec_boxes": [[10, 10, 40, 20]],
                        },
                    }
                }
            ]
        }
    }
    support = content_support(page, chain, pp)
    assert support["b0"]["bbox_pt"] == [10, 10, 40, 20]
    raw = pp["result"]["layoutParsingResults"][0]["prunedResult"]["overall_ocr_res"]
    raw["rec_texts"].append("source")
    raw["rec_boxes"].append([10, 40, 40, 50])
    assert content_support(page, chain, pp) == {}
    assert page["blocks"][0]["content"]["plain_text"] == "source"


def test_explicit_order_projection_changes_flow_without_characters() -> None:
    page, _ = fixture()
    page["blocks"] = [
        block(f"b{i}", 0, [0, 0, 10, 10], t, "inferred") for i, t in enumerate("ADBECF")
    ]
    page["reading_order"] = [b["id"] for b in page["blocks"]]
    order = ["b0", "b2", "b4", "b1", "b3", "b5"]
    from itertools import pairwise

    projected, proof = project_explicit_order(page, order, [list(p) for p in pairwise(order)])
    by_id = {b["id"]: b for b in projected["blocks"]}
    assert (
        "".join(by_id[bid]["content"]["plain_text"] for bid in projected["reading_order"])
        == "ABCDEF"
    )
    assert proof["atomic_coverage"] == "EXACT"


def test_selected_geometry_reaches_docx_and_source_map() -> None:
    """Synthetic source, real PDF/backend/writer; only model evidence is a fixture."""
    import shutil
    import uuid
    from pathlib import Path

    from prototypes.docx_output.common import PRIVATE, digest, read, save
    from prototypes.docx_output.geometry.candidate import full_page
    from prototypes.docx_output.geometry_arbitration import run
    from prototypes.docx_output.pipeline import convert
    from prototypes.docx_output.render_replay import inventory
    from tests.productization.synthetic.generate import pdf_bytes

    root = PRIVATE / ("arbitration-test-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    try:
        source = root / "source.pdf"
        source.write_bytes(pdf_bytes(b"BT /F1 14 Tf 30 340 Td (Source text) Tj ET"))
        original_job = convert(source, mode="native", output_root=root / "jobs")
        ir = read(original_job / "layout.auto.json")
        p = ir["pages"][0]
        info = ir["provenance"]["pages"]["0"]
        chain = full_page(p, info)
        texts, boxes = [], []
        for i, b in enumerate(p["blocks"]):
            assert b["content"]["kind"] == "text"
            bounds = list(b["bbox"])
            px0 = chain.to_input(bounds[0], bounds[1])
            px1 = chain.to_input(bounds[2], bounds[3])
            texts.append(b["content"]["plain_text"])
            boxes.append([*px0, *px1])
            p.setdefault("geometry_candidates", []).append(
                record(
                    "monkey",
                    0,
                    i,
                    "text",
                    "region",
                    "semantic_region",
                    [*px0, *px1],
                    "input_pixel",
                    chain,
                    {"fixture": True},
                )
            )
            b["geometry_source"] = "inferred"
            b["bbox"] = [0, 0, p["width_pt"], p["height_pt"]]
        save(original_job / "layout.auto.json", ir)
        pp = {
            "result": {
                "layoutParsingResults": [
                    {
                        "prunedResult": {
                            "width": info["pixel_size"][0],
                            "height": info["pixel_size"][1],
                            "model_settings": {"use_doc_preprocessor": False},
                            "parsing_res_list": [],
                            "overall_ocr_res": {"rec_texts": texts, "rec_boxes": boxes},
                        }
                    }
                ]
            }
        }
        response = original_job / "response-synthetic-pp.json"
        save(response, pp)
        save(
            original_job / "request-manifest.json",
            {
                "requests": [
                    {
                        "provider": "pp",
                        "page_index": 0,
                        "region_id": "synthetic",
                        "status": "COMPLETE",
                        "stored_response_sha256": digest(response),
                        "input_sha256": digest(original_job / info["image_path"]),
                    }
                ],
                "model_call_count": 0,
                "synthetic_evidence": True,
            },
        )
        seal = root / "seal.json"
        before = inventory(original_job)
        save(seal, {"artifacts": before})
        job = run(original_job, seal, root / "outputs")
        decision = read(job / "geometry-decisions.json")["pages"][0]
        projected = read(job / "layout.auto.json")["pages"][0]
        assert decision["status"] == "SELECTED" and decision["selected_provider"] == "monkey"
        assert projected["blocks"][0]["bbox"] != p["blocks"][0]["bbox"]
        assert projected["blocks"][0]["selected_geometry_id"].startswith("p0-monkey")
        assert (job / "auto.docx").is_file() and (job / "source-map.auto.json").is_file()
        assert read(job / "qa.json")["docx_package_valid"]
        assert inventory(original_job) == before
        assert read(job / "request-manifest.json")["model_call_count"] == 0
        assert Path(job / "render-plan.auto.json").is_file()
    finally:
        shutil.rmtree(root)
