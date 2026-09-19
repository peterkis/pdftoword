"""Line provenance, recomputed column proofs, and actual shared-stage conservation."""

from __future__ import annotations

import copy
from itertools import pairwise

import pytest
from prototypes.docx_output.common import DemoError, Json, block, relation
from prototypes.docx_output.geometry.candidate import TransformChain
from prototypes.docx_output.geometry.order import column_order, verify_order
from prototypes.docx_output.geometry.support import binding_ledger, content_support
from prototypes.docx_output.layout_rules import accept_candidate
from prototypes.docx_output.structure_processors.bridge import json_hash
from prototypes.docx_output.structure_processors.conservation import (
    continuation_rejection,
    verify_shared,
)


def columns() -> tuple[Json, Json]:
    p: Json = {
        "page_index": 0,
        "width_pt": 200,
        "height_pt": 200,
        "blocks": [],
        "reading_order": [],
    }
    supports = {}
    for i, text in enumerate("ADBECF"):
        x = 10 if i % 2 == 0 else 110
        y = 40 + (i // 2) * 25
        b = block(text, 0, [x, y, x + 70, y + 15], text, "pp_structure")
        p["blocks"].append(b)
        p["reading_order"].append(text)
        supports[text] = {
            "basis": "exact_pp_text",
            "bbox_pt": b["bbox"],
            "source_content_sha256": json_hash(b["content"]),
        }
    return p, supports


def pp_response(texts: list[str], boxes: list[list[int]]) -> Json:
    return {
        "result": {
            "layoutParsingResults": [
                {
                    "prunedResult": {
                        "width": 200,
                        "height": 200,
                        "model_settings": {"use_doc_preprocessor": False},
                        "overall_ocr_res": {"rec_texts": texts, "rec_boxes": boxes},
                    }
                }
            ]
        }
    }


def test_multiline_spans_cover_original_characters() -> None:
    b = block("b", 0, [0, 0, 200, 200], " Aβ 12\n中文 end ", "inferred")
    p = {"page_index": 0, "width_pt": 200, "height_pt": 200, "blocks": [b], "reading_order": ["b"]}
    response = pp_response(["Aβ 12", "中文 end"], [[10, 10, 60, 20], [10, 25, 60, 35]])
    chain = TransformChain((200, 200), (200, 200), (0, 0, 200, 200), (200, 200))
    support = content_support(p, chain, response)["b"]
    spans = support["line_fragments"]
    assert spans[0]["source_span"][0] == 0 and spans[-1]["source_span"][1] == len(
        b["content"]["plain_text"]
    )
    assert spans[0]["source_span"][1] == spans[1]["source_span"][0]
    assert support["bbox_pt"] == [10, 10, 60, 35] and not support["geometry_interpolation"]
    assert binding_ledger(p, {"b": support})["entries"][0]["status"] == "BOUND"


def test_shared_line_fragments_never_interpolate_boxes() -> None:
    a = block("a", 0, [0, 0, 200, 200], "left", "inferred")
    b = block("b", 0, [0, 0, 200, 200], "right", "inferred")
    p = {
        "page_index": 0,
        "width_pt": 200,
        "height_pt": 200,
        "blocks": [a, b],
        "reading_order": ["a", "b"],
    }
    chain = TransformChain((200, 200), (200, 200), (0, 0, 200, 200), (200, 200))
    response = pp_response(["left right"], [[10, 10, 190, 20]])
    support = content_support(p, chain, response)
    assert support["a"]["bbox_pt"] == support["b"]["bbox_pt"] == [10, 10, 190, 20]
    assert support["a"]["line_fragments"][0]["shared_line"]
    assert column_order(p, support)["status"] == "ABSTAIN"
    # Overlapping assignments to one source line cannot be double-counted.
    b["content"]["plain_text"] = "left right"
    assert content_support(p, chain, response) == {}


def test_column_proof_with_spanning_title_and_legacy_gate() -> None:
    p, support = columns()
    title = block("title", 0, [10, 5, 190, 20], "Title", "pp_structure", "heading")
    p["blocks"].insert(0, title)
    p["reading_order"].insert(0, "title")
    support["title"] = {
        "basis": "exact_pp_text",
        "bbox_pt": title["bbox"],
        "source_content_sha256": json_hash(title["content"]),
    }
    proof = column_order(p, support)
    assert proof["status"] == "PROVEN" and proof["order"] == ["title", *"ABCDEF"]
    projected = copy.deepcopy(p)
    projected["reading_order"] = proof["order"]
    old = {"pages": [p], "metadata": {}, "issues": [], "relations": []}
    new = {
        "pages": [projected],
        "metadata": {"column_order": {"0": proof}},
        "issues": [],
        "relations": [],
    }
    accept_candidate(old, new, projected)
    proof["edges"] = [list(edge) for edge in pairwise(p["reading_order"])]
    with pytest.raises(DemoError, match="PROOF"):
        accept_candidate(old, new, projected)


@pytest.mark.parametrize("fault", ["missing", "overlap", "locked", "fake_order"])
def test_column_proof_rejects_unsupported_reorder(fault: str) -> None:
    p, support = columns()
    if fault == "missing":
        support.pop("A")
    elif fault == "overlap":
        support["B"]["bbox_pt"] = [10, 40, 80, 55]
    elif fault == "locked":
        p["blocks"][1]["flags"].append("manual_lock")
    proof = column_order(p, support)
    if fault == "fake_order":
        projected = copy.deepcopy(p)
        projected["reading_order"] = list(reversed(proof["order"]))
        with pytest.raises(DemoError):
            verify_order(p, projected, proof)
    else:
        assert proof["status"] == "ABSTAIN"


def doc() -> Json:
    p, support = columns()
    return {"pages": [p], "relations": [], "metadata": {"geometry_support": {"0": support}}}


def test_relation_delta_preserves_source_and_rejects_cross_column() -> None:
    before = doc()
    p = before["pages"][0]
    p["reading_order"] = list("ABCDEF")
    after = copy.deepcopy(before)
    relation(after, "continuation_of", "B", "A", {"basis": "docvortex_public_postprocess"})
    assert verify_shared(before, after)["relation_delta"]["added"]
    after = copy.deepcopy(before)
    relation(after, "continuation_of", "D", "C", {"basis": "docvortex_public_postprocess"})
    with pytest.raises(DemoError, match="CROSS_COLUMN"):
        verify_shared(before, after)
    after = copy.deepcopy(before)
    relation(after, "caption_of", "B", "A", {"basis": "invented"})
    with pytest.raises(DemoError, match="UNPROVEN_RELATION"):
        verify_shared(before, after)


def test_question_gap_and_manual_relations_are_not_rewritten() -> None:
    before = doc()
    before["pages"][0]["blocks"][1]["type"] = "question"
    assert continuation_rejection(before, "B", "A") == "RELATION_CROSS_QUESTION"
    relation(before, "caption_of", "B", "A", {"manual": True})
    after = copy.deepcopy(before)
    after["relations"] = []
    with pytest.raises(DemoError, match="PROTECTED_RELATION"):
        verify_shared(before, after)
    after = copy.deepcopy(before)
    after["pages"][0]["blocks"][0]["content"]["plain_text"] = "corrected"
    with pytest.raises(DemoError):
        verify_shared(before, after)


def test_same_ids_do_not_hide_missing_or_repeated_content() -> None:
    before = doc()
    after = copy.deepcopy(before)
    after["pages"][0]["blocks"].pop()
    with pytest.raises(DemoError):
        verify_shared(before, after)


def test_actual_pp_path_reorders_columns_and_writes_docx() -> None:
    import shutil
    import uuid

    from docx import Document
    from PIL import Image
    from prototypes.docx_output.common import PRIVATE, layout, new_job
    from prototypes.docx_output.pipeline import finish, source_image
    from prototypes.docx_output.pp_layout import apply_pp_layout

    root = PRIVATE / ("column-gate-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    try:
        source = root / "source.png"
        Image.new("RGB", (200, 200), "white").save(source)
        job = new_job(root / "jobs")
        ir = layout(job, source, 1)
        p = source_image(job, ir, source)
        fixtures, _ = columns()
        p.update(
            width_pt=200,
            height_pt=200,
            blocks=fixtures["blocks"],
            reading_order=fixtures["reading_order"],
        )
        ir["provenance"]["pages"]["0"].update(pixel_to_point=[1, 1], point_to_pixel=[1, 1])
        boxes = [b["bbox"] for b in p["blocks"]]
        response = pp_response(list("ADBECF"), boxes)
        response["result"]["layoutParsingResults"][0]["prunedResult"]["parsing_res_list"] = [
            {"block_label": "text", "block_bbox": box, "block_content": text}
            for text, box in zip("ADBECF", boxes, strict=True)
        ]
        apply_pp_layout(job, ir, p, response, "synthetic-pp")
        assert p["reading_order"] == list("ABCDEF")
        assert ir["metadata"]["layout_validation"]["status"] == "APPLIED"
        assert ir["metadata"]["source_binding_ledger"]["0"]["source_inventory"][
            "input_order"
        ] == list("ADBECF")
        finish(job, ir)
        assert [
            paragraph.text
            for paragraph in Document(str(job / "auto.docx")).paragraphs
            if paragraph.text
        ] == list("ABCDEF")
    finally:
        shutil.rmtree(root)


def test_explicit_question_ownership_overrides_stream_position() -> None:
    before = doc()
    p = before["pages"][0]
    for qid in ("q1", "q2"):
        p["blocks"].append(block(qid, 0, [0, 0, 20, 10], qid, "inferred", "question"))
        p["reading_order"].append(qid)
    relation(before, "contains", "q1", "A", {})
    relation(before, "contains", "q2", "D", {})
    assert continuation_rejection(before, "D", "A") == "RELATION_CROSS_QUESTION"
    relation(before, "contains", "q1", "D", {})
    assert continuation_rejection(before, "D", "A") == "RELATION_AMBIGUOUS_OWNERSHIP"


def test_shared_stage_cannot_drop_content_candidates() -> None:
    before = doc()
    after = copy.deepcopy(before)
    after["pages"][0]["blocks"][0]["content_candidates"] = []
    with pytest.raises(DemoError, match="SHARED_ATOM_CHANGED"):
        verify_shared(before, after)


def test_column_gate_does_not_separate_existing_figure_ownership() -> None:
    p, support = columns()
    proof = column_order(p, support)
    projected = copy.deepcopy(p)
    projected["reading_order"] = proof["order"]
    edge = {"id": "ownership", "type": "caption_of", "from": "D", "to": "A"}
    old = {"pages": [p], "metadata": {}, "relations": [edge], "issues": []}
    new = {
        "pages": [projected],
        "metadata": {"column_order": {"0": proof}},
        "relations": [edge],
        "issues": [],
    }
    with pytest.raises(DemoError, match="RELATION_CROSSES_PROVEN_COLUMNS"):
        accept_candidate(old, new, projected)


def test_gate_accepts_changed_ids_at_measured_line_boundaries() -> None:
    b = block("source", 0, [0, 0, 200, 200], "first\nsecond", "inferred")
    page = {
        "page_index": 0,
        "width_pt": 200,
        "height_pt": 200,
        "blocks": [b],
        "reading_order": ["source"],
    }
    chain = TransformChain((200, 200), (200, 200), (0, 0, 200, 200), (200, 200))
    supports = content_support(
        page, chain, pp_response(["first", "second"], [[10, 10, 80, 20], [10, 30, 80, 40]])
    )
    before: Json = {"pages": [page], "metadata": {}, "relations": [], "issues": []}
    projected = copy.deepcopy(page)
    first, second = copy.deepcopy(b), copy.deepcopy(b)
    first.update(id="left", bbox=[10, 10, 80, 20], geometry_source="fused")
    first["content"]["plain_text"] = "first\n"
    second.update(id="right", bbox=[10, 30, 80, 40], geometry_source="fused")
    second["content"]["plain_text"] = "second"
    projected.update(blocks=[first, second], reading_order=["left", "right"])
    bindings = {
        "left": [{"source_id": "source", "start": 0, "end": 6}],
        "right": [{"source_id": "source", "start": 6, "end": 12}],
    }
    after: Json = {
        "pages": [projected],
        "metadata": {"source_bindings": {"0": bindings}, "geometry_support": {"0": supports}},
        "relations": [],
        "issues": [],
    }
    accept_candidate(before, after, projected)
    assert after["metadata"]["binding_validation"]["0"]["atomic_coverage"] == "EXACT"
    assert (
        after["metadata"]["binding_validation"]["0"]["geometry_support"]
        == "MEASURED_LINE_BOUNDARIES"
    )
    before["metadata"]["inline_parts"] = {"source": [{"kind": "formula"}]}
    with pytest.raises(DemoError, match="STYLED_ATOM"):
        accept_candidate(before, after, projected)
    before["metadata"].pop("inline_parts")
    first["bbox"] = [10, 10, 45, 20]
    with pytest.raises(DemoError, match="GEOMETRY_NOT_SOURCE_BOUND"):
        accept_candidate(before, after, projected)


def test_gate_rejects_splitting_inside_a_measured_line() -> None:
    b = block("source", 0, [0, 0, 200, 200], "abcd", "inferred")
    page = {
        "page_index": 0,
        "width_pt": 200,
        "height_pt": 200,
        "blocks": [b],
        "reading_order": ["source"],
    }
    chain = TransformChain((200, 200), (200, 200), (0, 0, 200, 200), (200, 200))
    support = content_support(page, chain, pp_response(["abcd"], [[10, 10, 80, 20]]))
    before: Json = {"pages": [page], "metadata": {}, "relations": [], "issues": []}
    projected = copy.deepcopy(page)
    one, two = copy.deepcopy(b), copy.deepcopy(b)
    one.update(id="one", bbox=[10, 10, 45, 20], geometry_source="fused")
    two.update(id="two", bbox=[45, 10, 80, 20], geometry_source="fused")
    one["content"]["plain_text"] = "ab"
    two["content"]["plain_text"] = "cd"
    projected.update(blocks=[one, two], reading_order=["one", "two"])
    after: Json = {
        "pages": [projected],
        "metadata": {
            "geometry_support": {"0": support},
            "source_bindings": {
                "0": {
                    "one": [{"source_id": "source", "start": 0, "end": 2}],
                    "two": [{"source_id": "source", "start": 2, "end": 4}],
                }
            },
        },
        "relations": [],
        "issues": [],
    }
    with pytest.raises(DemoError, match="INTERPOLATION_FORBIDDEN"):
        accept_candidate(before, after, projected)
