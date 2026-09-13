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
