"""Regression coverage for PR 3 review findings."""

from __future__ import annotations

import copy
from pathlib import Path, PureWindowsPath

import pytest
from prototypes.docx_output import common
from prototypes.docx_output.common import Json, block
from prototypes.docx_output.pipeline import finish
from prototypes.docx_output.review import apply_overrides
from prototypes.docx_output.structure import recover
from tests.demo.test_output import pp_block, raster, response, setup_ir


@pytest.mark.parametrize("anchor", ["C:/", "//server/share/"])
def test_windows_input_anchor(
    private_case: Path, monkeypatch: pytest.MonkeyPatch, anchor: str
) -> None:
    """Exercise validate_input's anchor split with Windows drive and UNC semantics."""
    source = raster(private_case)
    windows = PureWindowsPath(anchor) / "中文 空格" / source.name

    def check(root: Path, relative: str) -> Path:
        assert not PureWindowsPath(relative).is_absolute()
        assert PureWindowsPath(str(root)) / relative == windows
        return source

    with monkeypatch.context() as patch:
        patch.setattr(Path, "absolute", lambda self: windows)
        patch.setattr(common, "safe_path", check)
        common.validate_input(source)


def test_merge_retains_both_candidate_lineages(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("first", 0, [1, 1, 30, 20], "First", "native_pdf"),
        block("second", 0, [1, 21, 30, 40], "Second", "native_pdf"),
    ]
    p["reading_order"] = ["first", "second"]
    before = copy.deepcopy(p["blocks"])
    revised = apply_overrides(
        job,
        ir,
        {"operations": [{"block_id": "first", "action": "merge", "reason": "join paragraphs"}]},
    )
    merged = revised["pages"][0]["blocks"][0]
    candidates = {c["id"]: c for c in merged["content_candidates"]}
    for original in before:
        for c in original["content_candidates"]:
            assert candidates[c["id"]]["text"] == c["text"]
        assert (
            original["selected_candidate_id"]
            in candidates[merged["selected_candidate_id"]]["evidence"]["supersedes"]
        )
    assert revised["provenance"]["manual-0"]["merged_before"] == before[1]
    assert merged["content"]["plain_text"] == "First\nSecond"
    assert ir["pages"][0]["blocks"] == before


@pytest.mark.parametrize(
    "content",
    [
        "not a literal",
        "{}",
        "[{'label':'text','bbox':[1,2,3]}]",
        "[{'label':'text','bbox':[20,20,10,30]}]",
    ],
)
def test_optional_monkey_failure_preserves_pp(private_case: Path, content: str) -> None:
    job, ir, p = setup_ir(private_case)
    responses: Json = {
        "pp": response([pp_block("Preserved text")]),
        "monkey": {"choices": [{"finish_reason": "stop", "message": {"content": content}}]},
    }
    recover(job, ir, p, responses, {"requests": []})
    assert any(b["content"].get("plain_text") == "Preserved text" for b in p["blocks"])
    assert any(i["type"] == "MONKEY_CANDIDATE_REJECTED" for i in ir["issues"])
    qa = finish(job, ir)
    assert qa["execution_status"] == "COMPLETE"


@pytest.mark.parametrize("mode", ["ovis", "ovis-pp"])
@pytest.mark.parametrize("valid", [False, True])
def test_ovis_modes_keep_monkey_candidate(private_case: Path, mode: str, valid: bool) -> None:
    from prototypes.docx_output.pipeline import reconstruct

    job, ir, p = setup_ir(private_case)
    content = "[{'label':'text','bbox':[10,20,300,40]}]" if valid else "bad"
    responses = {
        "ovis": {"choices": [{"finish_reason": "stop", "message": {"content": "Preserved"}}]},
        "monkey": {"choices": [{"finish_reason": "stop", "message": {"content": content}}]},
    }
    reconstruct(job, ir, p, responses, {"requests": []}, mode)
    if valid:
        assert ir["provenance"]["monkey_geometry"]["0"][0]["raw_bbox"] == [10, 20, 300, 40]
    else:
        assert any(i["type"] == "MONKEY_CANDIDATE_REJECTED" for i in ir["issues"])
    assert p["blocks"][0]["content"]["plain_text"] == "Preserved"


def test_merge_marks_composed_geometry(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("a", 0, [1, 1, 30, 20], "First", "pp_structure"),
        block("b", 0, [1, 21, 30, 40], "Second", "inferred"),
    ]
    p["reading_order"] = ["a", "b"]
    revised = apply_overrides(
        job, ir, {"operations": [{"block_id": "a", "action": "merge", "reason": "join"}]}
    )
    assert revised["pages"][0]["blocks"][0]["geometry_source"] == "manual_correction"
    event = revised["provenance"]["manual-0"]
    assert event["before"]["geometry_source"] == "pp_structure"
    assert event["merged_before"]["geometry_source"] == "inferred"


def test_footer_join_keeps_both_candidates(private_case: Path) -> None:
    from prototypes.docx_output.ovis_replay import recover_ovis

    job, ir, p = setup_ir(private_case)
    recover_ovis(
        job,
        ir,
        p,
        {"choices": [{"finish_reason": "stop", "message": {"content": "第\n\n1页"}}]},
        "ovis",
    )
    footer = p["blocks"][0]
    originals = {c["text"]: c["id"] for c in footer["content_candidates"]}
    assert set(originals) == {"第", "1页", "第1页"}
    selected = next(c for c in footer["content_candidates"] if c["selected"])
    assert set(selected["evidence"]["supersedes"]) == {originals["第"], originals["1页"]}


@pytest.mark.parametrize("decoration", [b"10 10 575 820 re S\n", b"50 590 480 190 re S\n"])
def test_native_container_keeps_editable_text(private_case: Path, decoration: bytes) -> None:
    from prototypes.docx_output.pipeline import convert
    from tests.demo.synthetic import make_pdf

    source = private_case / "border.pdf"
    original = make_pdf(source, decoration=decoration)
    job = convert(source, output_root=private_case / "jobs")
    ir = common.read(job / "layout.auto.json")
    text = "".join(b["content"].get("plain_text", "") for b in ir["pages"][0]["blocks"])
    assert "".join(original.split()) == "".join(text.split())
    assert ir["pages"][0]["routing_decision"] == "NEEDS_ROUTE_REVIEW"


def test_split_right_candidate_has_supersedes(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    b = block("a", 0, [1, 1, 30, 20], "First Second", "native_pdf")
    p["blocks"] = [b]
    p["reading_order"] = ["a"]
    result = apply_overrides(
        job,
        ir,
        {"operations": [{"block_id": "a", "action": "split", "offset": 6, "reason": "split"}]},
    )
    right = result["pages"][0]["blocks"][1]
    selected = next(c for c in right["content_candidates"] if c["selected"])
    assert selected["evidence"]["supersedes"] == b["selected_candidate_id"]


def test_math_only_output_is_editable(private_case: Path) -> None:
    from prototypes.docx_output.ovis_replay import recover_ovis

    job, ir, p = setup_ir(private_case)
    recover_ovis(
        job,
        ir,
        p,
        {"choices": [{"finish_reason": "stop", "message": {"content": "$x^2$"}}]},
        "ovis",
    )
    qa = finish(job, ir)
    assert qa["omml_formula_count"] == 1
    assert qa["has_editable_runs"]
    assert qa["execution_status"] == "COMPLETE"


@pytest.mark.parametrize("kind", ["ocr", "formula"])
def test_pp_fine_boxes_outside_page_fall_back(private_case: Path, kind: str) -> None:
    from prototypes.docx_output.pp_layout import apply_pp_layout
    from tests.demo.test_layout_rules import case

    job, ir, p, pp = case(private_case)
    raw = pp["result"]["layoutParsingResults"][0]["prunedResult"]
    bbox = [-2, 20, 100, 50]
    if kind == "ocr":
        raw["overall_ocr_res"]["rec_boxes"].append(bbox)
    else:
        raw["formula_res_list"].append({"dt_polys": bbox})
    before = copy.deepcopy(p["blocks"])
    apply_pp_layout(job, ir, p, pp, "pp")
    assert ir["metadata"]["layout_validation"]["status"] == "FALLBACK"
    assert p["blocks"] == before


def test_caption_rows_cannot_cross_text(private_case: Path) -> None:
    from prototypes.docx_output.ovis_replay import associate_ovis

    _, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("f1", 0, [10, 10, 40, 40], "", "inferred", "figure"),
        block("c1", 0, [10, 40, 40, 45], "第1题", "inferred"),
        block("middle", 0, [10, 45, 80, 50], "Keep between", "inferred"),
        block("f2", 0, [50, 10, 80, 40], "", "inferred", "figure"),
        block("c2", 0, [50, 40, 80, 45], "第2题", "inferred"),
    ]
    associate_ovis(ir, p)
    groups = ir["metadata"]["figure_groups"]
    assert [len(g["pairs"]) for g in groups] == [1, 1]


def test_ambiguous_native_vectors_remain_in_output(private_case: Path) -> None:
    from prototypes.docx_output.pipeline import convert
    from tests.demo.synthetic import make_pdf

    source = private_case / "labeled-vector.pdf"
    make_pdf(source, decoration=b"50 700 300 70 re S\n")
    job = convert(source, output_root=private_case / "jobs")
    ir = common.read(job / "layout.auto.json")
    assert any("ambiguous_vector_reference" in b["flags"] for b in ir["pages"][0]["blocks"])
    assert any(i["type"] == "VECTOR_TEXT_OVERLAP_REVIEW" for i in ir["issues"])


def test_option_groups_do_not_cross_body(private_case: Path) -> None:
    from prototypes.docx_output.ovis_replay import associate_ovis

    _, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("a", 0, [1, 1, 20, 20], "A.", "inferred"),
        block("f1", 0, [1, 20, 20, 40], "", "inferred", "figure"),
        block("body", 0, [1, 40, 20, 60], "Between", "inferred"),
        block("b", 0, [30, 1, 50, 20], "B.", "inferred"),
        block("f2", 0, [30, 20, 50, 40], "", "inferred", "figure"),
    ]
    associate_ovis(ir, p)
    assert [len(g["pairs"]) for g in ir["metadata"]["figure_groups"]] == [1, 1]


def test_legacy_pp_rejects_outside_ocr(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    body = response([pp_block("Text")], [{"bbox": [-10, 20, 100, 40], "text": "Text"}])
    with pytest.raises(common.DemoError, match="PP_REGION_OUT_OF_PAGE"):
        recover(job, ir, p, {"pp": body}, {"requests": []})


def test_manual_crop_rejects_outside_page(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [block("a", 0, [1, 1, 20, 20], "Text", "native_pdf")]
    p["reading_order"] = ["a"]
    with pytest.raises(common.DemoError, match="INVALID_CROP"):
        apply_overrides(
            job,
            ir,
            {
                "operations": [
                    {"block_id": "a", "action": "crop", "bbox": [-1, 0, 30, 30], "reason": "crop"}
                ]
            },
        )


@pytest.mark.parametrize("outcome", ["success", "worker_failure", "validation_failure"])
def test_upload_temp_removed(
    private_case: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    import time

    from fastapi.testclient import TestClient
    from prototypes.docx_output import server

    upload_root = private_case / "staging"
    monkeypatch.setattr(server, "PRIVATE", upload_root)

    def work(*args: object, **kwargs: object) -> Path:
        if outcome == "worker_failure":
            raise common.DemoError("TEST_FAILURE")
        return private_case / "done"

    monkeypatch.setattr(server, "convert", work)
    with TestClient(
        server.create_app(output_root=private_case / "jobs"), base_url="http://127.0.0.1:8765"
    ) as client:
        token = client.get("/api/session").json()["token"]
        client.post(
            "/api/upload",
            files={
                "file": (
                    "input.png",
                    b"" if outcome == "validation_failure" else b"data",
                    "image/png",
                )
            },
            headers={"origin": "http://127.0.0.1:8765", "x-demo-session": token},
        )
        for _ in range(100):
            if not client.get("/api/status").json()["busy"]:
                break
            time.sleep(0.01)
    assert not list((upload_root / "uploads").glob("*/input.*"))


def test_table_image_counts_as_fallback(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    recover(job, ir, p, {"pp": response([pp_block("Table", label="table")])}, {"requests": []})
    qa = finish(job, ir)
    assert qa["fallback_region_count"] == 1
    assert qa["fallback_area_ratio"] > 0
    assert qa["placed_figure_count"] == 0


def test_merge_redirects_issue(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("a", 0, [1, 1, 20, 20], "A", "native_pdf"),
        block("b", 0, [1, 21, 20, 40], "B", "native_pdf"),
    ]
    p["reading_order"] = ["a", "b"]
    common.issue(ir, "CONTENT_CONFLICT", "Review", ["b"])
    result = apply_overrides(
        job, ir, {"operations": [{"block_id": "a", "action": "merge", "reason": "join"}]}
    )
    assert result["issues"][0]["block_ids"] == ["a"]


def test_legacy_option_groups_preserve_intervening_body(private_case: Path) -> None:
    from prototypes.docx_output.structure import associate

    _, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("a", 0, [1, 10, 9, 20], "A.", "inferred"),
        block("f1", 0, [10, 10, 30, 30], "", "inferred", "figure"),
        block("body", 0, [1, 40, 50, 60], "Middle", "inferred"),
        block("b", 0, [31, 10, 39, 20], "B.", "inferred"),
        block("f2", 0, [40, 10, 60, 30], "", "inferred", "figure"),
    ]
    associate(ir, p)
    assert all(len(g["pairs"]) == 1 for g in ir["metadata"]["figure_groups"])


def test_layout_acceptance_rejects_noncontiguous_text_group(private_case: Path) -> None:
    from prototypes.docx_output.layout_rules import accept_candidate
    from prototypes.docx_output.pp_layout import apply_pp_layout
    from tests.demo.test_layout_rules import case

    job, ir, p, pp = case(private_case)
    apply_pp_layout(job, ir, p, pp, "pp")
    original = copy.deepcopy(ir)
    group = ir["metadata"]["text_groups"][0]
    group["rows"][0] = [group["rows"][0][0], group["rows"][0][-1]]
    with pytest.raises(common.DemoError, match="NONCONTIGUOUS_LAYOUT_GROUP"):
        accept_candidate(original, ir, p)


def test_pp_ignores_other_page_relations(private_case: Path) -> None:
    from prototypes.docx_output.pp_layout import apply_pp_layout
    from tests.demo.test_layout_rules import case

    job, ir, p, pp = case(private_case)
    common.relation(ir, "caption_of", "other-caption", "other-image", {})
    apply_pp_layout(job, ir, p, pp, "pp")
    assert ir["metadata"]["layout_validation"]["status"] == "APPLIED"


def test_merge_transfers_relations(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("a", 0, [1, 1, 20, 20], "A", "native_pdf", "question"),
        block("b", 0, [1, 21, 20, 40], "B", "native_pdf", "question"),
        block("target", 0, [1, 50, 20, 70], "T", "native_pdf", "figure"),
    ]
    p["reading_order"] = ["a", "b", "target"]
    common.relation(ir, "references", "target", "b", {})
    result = apply_overrides(
        job, ir, {"operations": [{"block_id": "a", "action": "merge", "reason": "join"}]}
    )
    assert any(r["from"] == "target" and r["to"] == "a" for r in result["relations"])


def test_ovis_figure_has_one_display_group(private_case: Path) -> None:
    from prototypes.docx_output.ovis_replay import associate_ovis

    _, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("a", 0, [1, 1, 10, 10], "A.", "inferred"),
        block("f", 0, [10, 10, 30, 30], "", "inferred", "figure"),
        block("c", 0, [10, 31, 30, 40], "第1题", "inferred"),
    ]
    associate_ovis(ir, p)
    assert (
        sum(pair["figure"] == "f" for g in ir["metadata"]["figure_groups"] for pair in g["pairs"])
        == 1
    )
    assert any(r["type"] == "caption_of" for r in ir["relations"])


def test_legacy_caption_groups_split_vertical_rows(private_case: Path) -> None:
    from prototypes.docx_output.structure import associate

    _, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("f1", 0, [10, 10, 30, 30], "", "inferred", "figure"),
        block("c1", 0, [10, 31, 30, 40], "第1题", "inferred"),
        block("f2", 0, [10, 60, 30, 80], "", "inferred", "figure"),
        block("c2", 0, [10, 81, 30, 90], "第2题", "inferred"),
    ]
    associate(ir, p)
    assert [len(g["pairs"]) for g in ir["metadata"]["figure_groups"]] == [1, 1]


def test_auto_pp_split_retains_parent_candidate(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    text = "First text3. Next question"
    pp = response(
        [pp_block(text, bbox=[20, 20, 300, 80])],
        [
            {"text": "First text", "bbox": [20, 20, 300, 40]},
            {"text": "3. Next question", "bbox": [20, 60, 200, 80]},
        ],
    )
    recover(job, ir, p, {"pp": pp}, {})
    assert len(p["blocks"]) == 2
    for b in p["blocks"]:
        selected = next(c for c in b["content_candidates"] if c["selected"])
        assert selected["evidence"]["supersedes"] == "p0-b0-c0"
        assert ir["provenance"]["p0-b0"]["original_block"]["content_candidates"][0]["text"] == text


@pytest.mark.parametrize("formula", ["$x$", "$$x$$", "$$\nx^2\n$$"])
def test_formula_delimiters_leave_no_dollar_text(private_case: Path, formula: str) -> None:
    from prototypes.docx_output.ovis_replay import recover_ovis

    job, ir, p = setup_ir(private_case)
    recover_ovis(
        job,
        ir,
        p,
        {"choices": [{"finish_reason": "stop", "message": {"content": formula}}]},
        "ovis",
    )
    bid = p["blocks"][0]["id"]
    parts = ir["metadata"]["inline_parts"][bid]
    assert not any("$" in part.get("text", "") for part in parts)
    assert next(part for part in parts if "latex" in part)["source_text"] == formula.strip()


def test_layout_records_page_left_margin(private_case: Path) -> None:
    from prototypes.docx_output.pp_layout import apply_pp_layout
    from tests.demo.test_layout_rules import case

    job, ir, p, pp = case(private_case)
    apply_pp_layout(job, ir, p, pp, "pp")
    assert (
        ir["metadata"]["layout_by_page"]["0"]["content_left_pt"]
        == ir["metadata"]["content_left_pt"]
    )


@pytest.mark.parametrize("mode", ["ovis", "pp"])
def test_duplicate_question_number_never_binds_last(private_case: Path, mode: str) -> None:
    from prototypes.docx_output.ovis_replay import associate_ovis
    from prototypes.docx_output.structure import associate

    _, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("q1", 0, [1, 1, 90, 10], "1. First", "inferred", "question"),
        block("f", 0, [10, 20, 30, 40], "", "inferred", "figure"),
        block("c", 0, [10, 41, 30, 50], "第1题", "inferred"),
        block("q2", 0, [1, 70, 90, 80], "1. Other section", "inferred", "question"),
    ]
    (associate_ovis if mode == "ovis" else associate)(ir, p)
    assert not any(r["type"] == "references" for r in ir["relations"])
    assert any(i["type"] == "AMBIGUOUS_QUESTION_NUMBER" for i in ir["issues"])


def test_offline_preview_uses_reviewed_order(private_case: Path) -> None:
    from prototypes.docx_output.review import write_preview

    job, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("a", 0, [1, 1, 20, 20], "First marker", "native_pdf"),
        block("b", 0, [1, 21, 20, 40], "Second marker", "native_pdf"),
    ]
    p["reading_order"] = ["a", "b"]
    result = apply_overrides(
        job,
        ir,
        {"operations": [{"block_id": "b", "action": "move", "delta": -1, "reason": "move"}]},
    )
    write_preview(job, result, "reviewed")
    html = (job / "review" / "reviewed.html").read_text()
    assert html.index("Second marker") < html.index("First marker")


def test_ovis_single_newline_question_boundary(private_case: Path) -> None:
    from prototypes.docx_output.ovis_replay import recover_ovis

    job, ir, p = setup_ir(private_case)
    raw = "1. First\nA. Choice\n2. Second\nA. $$x+\n3. y$$"
    recover_ovis(
        job, ir, p, {"choices": [{"finish_reason": "stop", "message": {"content": raw}}]}, "ovis"
    )
    assert [b["type"] for b in p["blocks"]] == ["question", "option", "question", "option"]
    assert all(
        c["evidence"]["raw_markdown_paragraph"] == raw
        for b in p["blocks"]
        for c in b["content_candidates"]
    )


def test_pp_provenance_is_page_keyed(private_case: Path) -> None:
    from prototypes.docx_output.pp_layout import apply_pp_layout
    from tests.demo.test_layout_rules import case

    job, ir, p, pp = case(private_case)
    ir["provenance"]["pp_layout_only"] = {"earlier": {"request_id": "previous"}}
    apply_pp_layout(job, ir, p, pp, "current")
    assert ir["provenance"]["pp_layout_only"]["earlier"]["request_id"] == "previous"
    assert ir["provenance"]["pp_layout_only"]["0"]["request_id"] == "current"


@pytest.mark.parametrize("kind", ["label_of", "caption_of", "references"])
def test_manual_relation_rejects_wrong_endpoint_types(private_case: Path, kind: str) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("a", 0, [1, 1, 20, 20], "A", "native_pdf"),
        block("b", 0, [1, 21, 20, 40], "B", "native_pdf"),
    ]
    p["reading_order"] = ["a", "b"]
    with pytest.raises(common.DemoError, match="INVALID_RELATION_TARGET"):
        apply_overrides(
            job,
            ir,
            {
                "operations": [
                    {
                        "block_id": "a",
                        "action": "relation",
                        "target_id": "b",
                        "relation_type": kind,
                        "reason": "link",
                    }
                ]
            },
        )


def test_large_native_frame_is_not_ordinary_figure(private_case: Path) -> None:
    from prototypes.docx_output.pipeline import convert
    from tests.demo.synthetic import make_pdf

    source = private_case / "frame.pdf"
    make_pdf(source, decoration=b"10 10 575 820 re S\n")
    job = convert(source, output_root=private_case / "jobs")
    ir = common.read(job / "layout.auto.json")
    p = ir["pages"][0]
    assert all(
        common.area(b["bbox"]) < p["width_pt"] * p["height_pt"] * 0.5
        for b in p["blocks"]
        if b["type"] == "figure"
    )


def test_merge_quarantines_invalid_relation_types(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("q", 0, [1, 1, 20, 20], "1. Q", "native_pdf", "question"),
        block("c", 0, [1, 21, 20, 40], "Caption", "native_pdf", "caption"),
        block("f", 0, [1, 50, 20, 70], "", "inferred", "figure"),
    ]
    p["reading_order"] = ["q", "c", "f"]
    common.relation(ir, "caption_of", "c", "f", {})
    result = apply_overrides(
        job, ir, {"operations": [{"block_id": "q", "action": "merge", "reason": "join"}]}
    )
    assert not any(r["type"] == "caption_of" for r in result["relations"])
    assert any(i["type"] == "MERGED_RELATION_REVIEW" for i in result["issues"])


def test_background_image_does_not_suppress_native_text(private_case: Path) -> None:
    from prototypes.docx_output.pipeline import convert
    from tests.demo.synthetic import make_pdf

    source = private_case / "background.pdf"
    original = make_pdf(source, background=True)
    job = convert(source, output_root=private_case / "jobs")
    ir = common.read(job / "layout.auto.json")
    text = "".join(b["content"].get("plain_text", "") for b in ir["pages"][0]["blocks"])
    assert "".join(original.split()) == "".join(text.split())


def test_relation_id_never_collides_after_delete() -> None:
    ir: Json = {"relations": []}
    common.relation(ir, "references", "a", "b", {})
    common.relation(ir, "references", "c", "d", {})
    ir["relations"].pop(0)
    common.relation(ir, "references", "e", "f", {})
    assert len({r["id"] for r in ir["relations"]}) == 2


@pytest.mark.parametrize("raw", [r"1. 求 \sqrt{x}", r"x\leq0", r"$x$ and \alpha"])
def test_unprocessed_latex_never_exports_as_plain_text(private_case: Path, raw: str) -> None:
    from prototypes.docx_output.ovis_replay import recover_ovis

    job, ir, p = setup_ir(private_case)
    recover_ovis(
        job, ir, p, {"choices": [{"finish_reason": "stop", "message": {"content": raw}}]}, "ovis"
    )
    with pytest.raises(common.DemoError, match="UNRENDERED_MATH_REQUIRES_REVIEW"):
        finish(job, ir)


def test_small_background_keeps_native_text_and_requires_review(private_case: Path) -> None:
    from prototypes.docx_output.pipeline import convert
    from tests.demo.synthetic import make_pdf

    source = private_case / "small-bg.pdf"
    original = make_pdf(source, decoration=b"q 500 0 0 190 40 600 cm /Im0 Do Q\n")
    job = convert(source, output_root=private_case / "jobs")
    ir = common.read(job / "layout.auto.json")
    p = ir["pages"][0]
    text = "".join(b["content"].get("plain_text", "") for b in p["blocks"])
    assert "".join(original.split()) == "".join(text.split())
    assert p["routing_decision"] == "NEEDS_ROUTE_REVIEW"


@pytest.mark.parametrize("raw", [r"C:\Users\Alice", r"regex \w+ and \d+", r"$x$ at C:\Users\Alice"])
def test_plain_backslashes_remain_editable(private_case: Path, raw: str) -> None:
    from prototypes.docx_output.ovis_replay import recover_ovis

    job, ir, p = setup_ir(private_case)
    recover_ovis(
        job, ir, p, {"choices": [{"finish_reason": "stop", "message": {"content": raw}}]}, "ovis"
    )
    assert finish(job, ir)["has_editable_runs"]


def test_large_inset_vector_is_retained(private_case: Path) -> None:
    from prototypes.docx_output.pipeline import convert
    from tests.demo.synthetic import make_pdf

    source = private_case / "large-diagram.pdf"
    make_pdf(source, decoration=b"40 40 500 750 re S\n")
    job = convert(source, output_root=private_case / "jobs")
    p = common.read(job / "layout.auto.json")["pages"][0]
    assert any(
        common.area(b["bbox"]) > p["width_pt"] * p["height_pt"] * 0.5
        for b in p["blocks"]
        if b["type"] == "figure"
    )


def test_crop_label_detaches_inline_group(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("a", 0, [1, 1, 20, 20], "A.", "native_pdf"),
        block("f", 0, [20, 1, 40, 20], "Figure", "native_pdf"),
    ]
    p["reading_order"] = ["a", "f"]
    ir["metadata"]["figure_groups"] = [
        {
            "page_index": 0,
            "kind": "option_grid",
            "inline_labels": True,
            "pairs": [{"label": "a", "figure": "f"}],
        }
    ]
    result = apply_overrides(
        job,
        ir,
        {
            "operations": [
                {"block_id": "a", "action": "crop", "bbox": [1, 1, 20, 20], "reason": "crop"}
            ]
        },
    )
    assert not result["metadata"]["figure_groups"]
    finish(job, result)


def test_legacy_pp_plain_path_remains_text(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    recover(job, ir, p, {"pp": response([pp_block(r"C:\Users\Alice")])}, {})
    assert p["blocks"][0]["content"]["kind"] == "text"
    assert finish(job, ir)["fallback_region_count"] == 0


def test_editing_inline_label_releases_group(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("a", 0, [1, 1, 20, 20], "A.", "native_pdf"),
        block("f", 0, [20, 1, 40, 20], "Figure", "native_pdf"),
    ]
    p["reading_order"] = ["a", "f"]
    ir["metadata"]["figure_groups"] = [
        {
            "page_index": 0,
            "kind": "option_grid",
            "inline_labels": True,
            "pairs": [{"label": "a", "figure": "f"}],
        }
    ]
    result = apply_overrides(
        job,
        ir,
        {
            "operations": [
                {"block_id": "a", "action": "text", "text": "A. $x^2$", "reason": "formula"}
            ]
        },
    )
    assert not result["metadata"]["figure_groups"]
    assert finish(job, result)["omml_formula_count"] == 1


def test_currency_pair_is_not_silently_math(private_case: Path) -> None:
    from prototypes.docx_output.ovis_replay import recover_ovis

    job, ir, p = setup_ir(private_case)
    raw = "Price $5 and $4"
    recover_ovis(
        job, ir, p, {"choices": [{"finish_reason": "stop", "message": {"content": raw}}]}, "ovis"
    )
    assert not ir["metadata"].get("inline_parts")
    assert finish(job, ir)["has_editable_runs"]


def test_pdf_manifest_records_actual_page_count(private_case: Path) -> None:
    from prototypes.docx_output.pipeline import convert
    from tests.demo.synthetic import make_pdf

    source = private_case / "two.pdf"
    make_pdf(source, pages=2)
    job = convert(source, output_root=private_case / "jobs")
    assert common.read(job / "input-manifest.json")["page_count"] == 2


def test_pp_overlap_retains_text(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    pp = response([pp_block("", label="image", bbox=[1, 1, 399, 599]), pp_block("Keep editable")])
    recover(job, ir, p, {"pp": pp}, {})
    assert any(b["content"].get("plain_text") == "Keep editable" for b in p["blocks"])
    assert any(i["type"] == "IMAGE_TEXT_OVERLAP_REVIEW" for i in ir["issues"])


def test_split_overlap_issue_targets_children(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    pp = response(
        [
            pp_block("", label="image", bbox=[1, 1, 399, 599]),
            pp_block("First3. Next", bbox=[20, 20, 300, 80]),
        ],
        [
            {"text": "First", "bbox": [20, 20, 300, 40]},
            {"text": "3. Next", "bbox": [20, 60, 200, 80]},
        ],
    )
    recover(job, ir, p, {"pp": pp}, {})
    ids = {b["id"] for b in p["blocks"]}
    assert all(set(i["block_ids"]) <= ids for i in ir["issues"])


def test_manual_plain_path_stays_editable(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [block("a", 0, [1, 1, 20, 20], "Original", "native_pdf")]
    p["reading_order"] = ["a"]
    result = apply_overrides(
        job,
        ir,
        {
            "operations": [
                {"block_id": "a", "action": "text", "text": r"C:\Users\Alice", "reason": "edit"}
            ]
        },
    )
    assert result["pages"][0]["blocks"][0]["content"]["plain_text"] == r"C:\Users\Alice"


def test_split_rejects_parent_ovis_candidate(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    b = block("a", 0, [1, 1, 20, 20], "First Second", "ovis_ocr2")
    p["blocks"] = [b]
    p["reading_order"] = ["a"]
    operations = [
        {"block_id": "a", "action": "split", "offset": 6, "reason": "split"},
        {
            "block_id": "a",
            "action": "candidate",
            "candidate_id": b["selected_candidate_id"],
            "reason": "accept",
        },
    ]
    with pytest.raises(common.DemoError, match="CANDIDATE_NOT_FOUND"):
        apply_overrides(job, ir, {"operations": operations})


@pytest.mark.parametrize("choices", [{"x": 1}, [None], [{"message": None}], None])
def test_malformed_chat_shapes_raise_domain_error(choices: object) -> None:
    from prototypes.docx_output.structure import chat_content

    with pytest.raises(common.DemoError, match="INVALID_CANDIDATE_WIRE_TYPE"):
        chat_content({"choices": choices})


@pytest.mark.parametrize("page_level", [False, True])
def test_issue_resolution_can_empty_queue(private_case: Path, page_level: bool) -> None:
    job, ir, p = setup_ir(private_case)
    if not page_level:
        p["blocks"] = [block("a", 0, [1, 1, 20, 20], "Text", "native_pdf")]
        p["reading_order"] = ["a"]
    common.issue(ir, "REVIEW", "Check", [] if page_level else ["a"])
    op = {
        "action": "resolve_issue",
        "issue_id": ir["issues"][0]["id"],
        "page_index": 0,
        "reason": "checked",
    }
    if not page_level:
        op["block_id"] = "a"
    result = apply_overrides(job, ir, {"operations": [op]})
    assert all(i["status"] == "resolved" for i in result["issues"])
    assert result["provenance"]["manual-0"]["operation"] == op


@pytest.mark.parametrize(
    "raw", ["**1. Question**", "- Choice", "| A | B |\n|---|---|", "*1. Question*", "_A. Choice_"]
)
def test_unsupported_markdown_requires_review(private_case: Path, raw: str) -> None:
    from prototypes.docx_output.ovis_replay import recover_ovis

    job, ir, p = setup_ir(private_case)
    recover_ovis(
        job,
        ir,
        p,
        {"choices": [{"finish_reason": "stop", "message": {"content": raw}}]},
        "ovis",
    )
    assert ir["provenance"]["ovis_content"]["0"] == raw

    qa = finish(job, ir)
    assert (job / "auto.docx").exists()
    assert qa["fallback_area_ratio"] == pytest.approx(1)
    assert any(i["type"] == "OVIS_MARKDOWN_REVIEW_REQUIRED" for i in ir["issues"])


def test_crop_invalidates_text_caption_relation(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("c", 0, [1, 1, 20, 20], "Caption", "native_pdf", "caption"),
        block("f", 0, [20, 1, 40, 20], "", "inferred", "figure"),
    ]
    p["reading_order"] = ["c", "f"]
    common.relation(ir, "caption_of", "c", "f", {})
    result = apply_overrides(
        job, ir, {"operations": [{"block_id": "c", "action": "crop", "reason": "crop"}]}
    )
    assert not result["relations"]
    assert any(i["type"] == "MANUAL_RELATION_REVIEW" for i in result["issues"])


def test_resolved_issue_not_listed_as_pending(private_case: Path) -> None:
    from prototypes.docx_output.review import write_preview

    job, ir, _ = setup_ir(private_case)
    common.issue(ir, "UNIQUE_RESOLVED", "Already checked", [])
    ir["issues"][0]["status"] = "resolved"
    write_preview(job, ir, "reviewed")
    assert "UNIQUE_RESOLVED" not in (job / "review" / "reviewed.html").read_text()


@pytest.mark.parametrize(
    "text,offset,kind", [("1. First 2. Next", 9, "question"), ("C. First D. Next", 9, "option")]
)
def test_manual_split_classifies_right(
    private_case: Path, text: str, offset: int, kind: str
) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [block("a", 0, [1, 1, 20, 20], text, "native_pdf")]
    p["reading_order"] = ["a"]
    result = apply_overrides(
        job,
        ir,
        {"operations": [{"block_id": "a", "action": "split", "offset": offset, "reason": "split"}]},
    )
    assert result["pages"][0]["blocks"][1]["type"] == kind


@pytest.mark.parametrize("raw", ["*1. Question\ncontinued*", "_A. Choice\ncontinued_"])
def test_multiline_emphasis_falls_back(private_case: Path, raw: str) -> None:
    from prototypes.docx_output.ovis_replay import recover_ovis

    job, ir, p = setup_ir(private_case)
    recover_ovis(
        job, ir, p, {"choices": [{"finish_reason": "stop", "message": {"content": raw}}]}, "ovis"
    )
    assert finish(job, ir)["fallback_area_ratio"] == pytest.approx(1)


def test_browser_split_uses_codepoint_offset() -> None:
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("Node runtime required for browser handler test")
    script = (common.ROOT / "prototypes/docx_output/static/app.js").read_text()
    handler = next(line for line in script.splitlines() if line.startswith("on('split'"))
    fixture = (
        "const callbacks={};function on(name,cb){callbacks[name]=cb;}"
        'function $(id){return {value:"𠮷😀AB",selectionStart:4};}'
        "function operation(op){console.log(JSON.stringify(op));}"
    )
    result = subprocess.run(
        [node, "-e", fixture + handler + ";callbacks.split();"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout)["offset"] == 2


@pytest.mark.parametrize(
    "initial,text,expected",
    [("paragraph", "1. Correct question", "question"), ("question", "Plain body", "paragraph")],
)
def test_edit_reclassifies_confirmed_text(
    private_case: Path, initial: str, text: str, expected: str
) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [block("a", 0, [1, 1, 20, 20], "Old", "native_pdf", initial)]
    p["reading_order"] = ["a"]
    result = apply_overrides(
        job,
        ir,
        {"operations": [{"block_id": "a", "action": "text", "text": text, "reason": "correct"}]},
    )
    assert result["pages"][0]["blocks"][0]["type"] == expected


@pytest.mark.parametrize("kind", ["heading", "footer", "caption"])
def test_text_edit_preserves_nonlexical_type(private_case: Path, kind: str) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [block("a", 0, [1, 1, 20, 20], "Old", "native_pdf", kind)]
    p["reading_order"] = ["a"]
    result = apply_overrides(
        job,
        ir,
        {
            "operations": [
                {"block_id": "a", "action": "text", "text": "Corrected", "reason": "typo"}
            ]
        },
    )
    assert result["pages"][0]["blocks"][0]["type"] == kind


@pytest.mark.parametrize("role", ["member", "question"])
def test_reclassification_detaches_text_groups(private_case: Path, role: str) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("q", 0, [1, 1, 20, 20], "1. Q", "native_pdf", "question"),
        block("a", 0, [1, 21, 20, 40], "A. Choice", "native_pdf", "option"),
    ]
    p["reading_order"] = ["q", "a"]
    ir["metadata"]["text_groups"] = [
        {"page_index": 0, "question_id": "q", "columns": 1, "rows": [["a"]]}
    ]
    op = {
        "block_id": "a" if role == "member" else "q",
        "action": "text",
        "text": "2. New" if role == "member" else "Body",
        "reason": "correct",
    }
    result = apply_overrides(job, ir, {"operations": [op]})
    assert not result["metadata"]["text_groups"]


def test_split_label_detaches_old_association(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    p["blocks"] = [
        block("a", 0, [1, 1, 20, 20], "A.", "native_pdf", "option"),
        block("f", 0, [20, 1, 40, 20], "", "inferred", "figure"),
    ]
    p["reading_order"] = ["a", "f"]
    common.relation(ir, "label_of", "a", "f", {})
    ir["metadata"]["figure_groups"] = [
        {"page_index": 0, "kind": "option_grid", "pairs": [{"label": "a", "figure": "f"}]}
    ]
    result = apply_overrides(
        job,
        ir,
        {"operations": [{"block_id": "a", "action": "split", "offset": 1, "reason": "split"}]},
    )
    assert result["pages"][0]["blocks"][0]["type"] == "paragraph"
    assert not result["metadata"]["figure_groups"]
    assert not result["relations"] or all(r["type"] != "label_of" for r in result["relations"])


def test_revision_switch_restores_preview_assets() -> None:
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("Node required")
    script = (common.ROOT / "prototypes/docx_output/static/app.js").read_text()
    handler = next(
        line for line in script.splitlines() if line.startswith("$('revision').onchange")
    )
    fixture = (
        "let preview=true,unsavedPreview=true,revision='reviewed';"
        "let data={auto:{},reviewed:{}},layout;const el={value:'auto'};"
        "function $(){return el;}function message(){}function show(){};"
    )
    result = subprocess.run(
        [
            node,
            "-e",
            fixture
            + handler
            + "el.onchange();el.value='reviewed';el.onchange();console.log(preview);",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "true"


@pytest.mark.parametrize("raw", ["Price $5", "Price $5 and $4"])
def test_currency_exports_as_literal_text(private_case: Path, raw: str) -> None:
    from prototypes.docx_output.ovis_replay import recover_ovis

    job, ir, p = setup_ir(private_case)
    recover_ovis(
        job, ir, p, {"choices": [{"finish_reason": "stop", "message": {"content": raw}}]}, "ovis"
    )
    assert finish(job, ir)["has_editable_runs"]
    assert p["blocks"][0]["content"]["plain_text"] == raw


def test_invalid_native_xml_char_falls_back(
    private_case: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pypdfium2 as pdfium  # type: ignore[import-untyped]
    from prototypes.docx_output.pipeline import convert
    from tests.demo.synthetic import make_pdf

    source = private_case / "invalid-char.pdf"
    make_pdf(source)
    original = pdfium.raw.FPDFText_GetUnicode
    monkeypatch.setattr(
        pdfium.raw,
        "FPDFText_GetUnicode",
        lambda page, index: 1 if index == 0 else original(page, index),
    )
    job = convert(source, output_root=private_case / "jobs")
    ir = common.read(job / "layout.auto.json")
    assert any(i["type"] == "INVALID_XML_TEXT_FALLBACK" for i in ir["issues"])
    assert common.read(job / "qa.json")["fallback_region_count"] > 0


@pytest.mark.parametrize("raw", [r"\(x^2\)", r"\[a+b\]"])
def test_standard_latex_delimiters_require_handling(raw: str) -> None:
    from prototypes.docx_output.formula import unrendered_math

    assert unrendered_math(raw)


@pytest.mark.parametrize("raw", ["US$5", "HK$100", "A$20"])
def test_currency_prefix_remains_literal(private_case: Path, raw: str) -> None:
    from prototypes.docx_output.ovis_replay import recover_ovis

    job, ir, p = setup_ir(private_case)
    recover_ovis(
        job, ir, p, {"choices": [{"finish_reason": "stop", "message": {"content": raw}}]}, "ovis"
    )
    assert finish(job, ir)["has_editable_runs"]


def test_currency_then_formula_parses_independently(private_case: Path) -> None:
    from prototypes.docx_output.ovis_replay import recover_ovis

    job, ir, p = setup_ir(private_case)
    raw = "US$5 and $x$"
    recover_ovis(
        job, ir, p, {"choices": [{"finish_reason": "stop", "message": {"content": raw}}]}, "ovis"
    )
    parts = ir["metadata"]["inline_parts"][p["blocks"][0]["id"]]
    assert [x["latex"] for x in parts if "latex" in x] == ["x"]
    assert finish(job, ir)["omml_formula_count"] == 1


def test_preview_crop_does_not_overwrite_saved_bytes(private_case: Path) -> None:
    job, ir, p = setup_ir(private_case)
    first = common.crop(job, ir, p, [1, 1, 20, 20], "same")
    asset = next(a for a in ir["assets"] if a["id"] == first)
    path = job / asset["path"]
    before = path.read_bytes()
    other = copy.deepcopy(ir)
    other["assets"] = []
    common.crop(job, other, p, [1, 1, 100, 100], "same")
    assert path.read_bytes() == before
    assert other["assets"][0]["path"] != asset["path"]


@pytest.mark.parametrize("mode", ["ovis", "native"])
def test_alternate_math_exports_reviewable_fallback(private_case: Path, mode: str) -> None:
    from prototypes.docx_output.ovis_replay import recover_ovis
    from prototypes.docx_output.pipeline import convert
    from tests.demo.synthetic import make_pdf

    if mode == "ovis":
        job, ir, p = setup_ir(private_case)
        recover_ovis(
            job,
            ir,
            p,
            {"choices": [{"finish_reason": "stop", "message": {"content": r"\(x^2\)"}}]},
            "ovis",
        )
        qa = finish(job, ir)
    else:
        source = private_case / "math.pdf"
        text = r"\(x^2\)".encode("utf-16-be").hex()
        make_pdf(source, decoration=f"BT /F1 12 Tf 60 580 Td <{text}> Tj ET\n".encode())
        job = convert(source, output_root=private_case / "jobs")
        qa = common.read(job / "qa.json")
    assert qa["fallback_region_count"] > 0
    assert (job / "auto.docx").exists()
