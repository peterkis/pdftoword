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
