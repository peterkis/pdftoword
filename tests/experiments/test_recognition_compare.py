"""Adversarial and controlled tests for comparison integrity, never quality acceptance."""

from __future__ import annotations

import copy
import socket
import zipfile
from pathlib import Path
from typing import Any

import pytest
from experiments.recognition_compare import common, evaluate, prepare, report, runner


def reference(kind: str = "text", box: list[int] | None = None) -> common.Json:
    """A synthetic source-bound scoring unit."""
    return {
        "id": "a",
        "bbox": box or [0, 0, 100, 20],
        "kind": kind,
        "text": "abc",
        "policy": "score",
        "raw": {},
        "human_confirmed": False,
    }


def prediction(box: list[int] | None = None, kind: str = "text") -> common.Json:
    """A synthetic prediction with an explicit geometry and order."""
    return {
        "id": "p",
        "bbox": box or [0, 0, 100, 20],
        "kind": kind,
        "text": "abc",
        "order": 0,
        "discarded": False,
    }


def test_geometry_before_text_and_ambiguity() -> None:
    """Matching strings at another location cannot erase omissions or duplicated anchors."""
    ref = reference()
    assert evaluate.align([ref], [prediction([200, 200, 300, 220])])[0]["status"] == "MISSING"
    duplicate = {**ref, "id": "b"}
    matches = evaluate.align([ref, duplicate], [prediction()])
    assert all(m["status"] == "ALIGNMENT_REVIEW" for m in matches)
    assert evaluate.align([ref], [{**prediction(), "discarded": True}])[0]["status"] == "MISSING"


def test_split_lines_many_to_one() -> None:
    """Multiple geometrically contained prediction fragments remain explicit."""
    outputs = [prediction([0, 0, 40, 20]), {**prediction([40, 0, 100, 20]), "id": "p2", "order": 1}]
    result = evaluate.align([reference()], outputs)[0]
    assert result["status"] == "MATCHED"
    assert len(result["outputs"]) == 2


def test_missing_cer_is_not_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing known text remains in the denominator with all characters deleted."""
    monkeypatch.setattr(evaluate, "reference_units", lambda _: [reference()])
    result = evaluate.score_page({"reading_order_edges": [], "relationships": []}, [])
    assert result["matches"][0]["cer"]["deletions"] == 3
    assert result["matches"][0]["cer"]["value"] == 1


def test_normalization_does_not_correct_source() -> None:
    """Only Unicode composition and newline encoding can change."""
    assert evaluate.norm("e\u0301\r\nA １２") == "é\nA １２"
    assert evaluate.norm("a") != evaluate.norm("A")


def test_table_blank_and_merged_cells() -> None:
    """HTML spans, actual blank cells and row/column identity are measured."""
    grid = evaluate.grid_from_html(
        '<table><tr><td rowspan="2">a</td><td></td></tr><tr><td>b</td></tr></table>'
    )
    assert grid["rows"] == 2 and grid["columns"] == 2
    assert grid["cells"][2]["col"] == 1
    expected = {**grid, "cells": [{**c, "anchor_id": str(i)} for i, c in enumerate(grid["cells"])]}
    check = evaluate.table_comparison(expected, grid)
    assert all(c["text_equal"] and c["span_equal"] for c in check["cells"])
    assert sum(c["blank"] for c in check["cells"]) == 1


def test_formula_context_and_owner_image_excluded() -> None:
    """Do not turn formula context indexes or owner-excluded picture text into extra equations."""
    page: common.Json = {
        "anchors": [{"id": "f", "bbox": [0, 0, 10, 10]}],
        "blocks": [],
        "figures": [],
        "tables": [],
        "formulas": [{"anchor_id": "f", "text": "x", "subtype": "line_context"}],
    }
    assert evaluate.reference_units(page)[0]["policy"] == "context_only"
    page["formulas"][0] = {
        "anchor_id": "f",
        "text": "x",
        "comparison_review": {"policy": "preserve_image"},
    }
    assert evaluate.reference_units(page)[0]["policy"] == "preserve_image"


def test_edits_bind_and_preserve_original() -> None:
    """Apply to all repeated representations, without mutating the original draft."""
    annotation = {
        "sample_id": "s",
        "source": {"uploaded_filename": "mix.pdf"},
        "pages": [
            {
                "page": 1,
                "anchors": [{"id": "a", "bbox": [0, 0, 10, 10]}],
                "blocks": [{"anchor_id": "a", "text": "old", "text_lines": ["old"]}],
            }
        ],
    }
    original = copy.deepcopy(annotation)
    edit = {
        "sample_id": "s",
        "page": 1,
        "anchor_id": "a",
        "text": "new",
        "bbox": [1, 1, 9, 9],
        "decision": "CORRECTED_DRAFT",
        "note": "图的一部分",
    }
    result, changes = prepare.apply_edits(annotation, [edit])
    assert annotation == original
    assert result["pages"][0]["blocks"][0]["text_lines"] == ["new"]
    assert changes[0]["policy"] == "preserve_image"
    with pytest.raises(common.ExperimentError, match="EDIT_ANCHOR"):
        prepare.apply_edits(annotation, [{**edit, "anchor_id": "wrong"}])


@pytest.mark.parametrize("arm", ["B", "C"])
def test_online_ocr_is_per_file(arm: str) -> None:
    """The exact API contract requires OCR under files[], including the Russian group."""
    body = runner.request_body("G5", {"pages": [3], "language": "cyrillic"}, arm, "test")
    assert body["files"][0]["is_ocr"] is True
    assert body["files"][0]["page_ranges"] == "1-1"
    assert body["language"] == "cyrillic"
    assert body["enable_formula"] and body["enable_table"]
    assert "is_ocr" not in body and "effort" not in body


@pytest.mark.parametrize(
    "url",
    ["http://mineru.net/x", "https://evil.example/x", "https://token@cdn-mineru.openxlab.org.cn/x"],
)
def test_external_origin_rejected(url: str) -> None:
    """A remote result cannot redirect the adapter toward arbitrary destinations."""
    with pytest.raises(common.ExperimentError, match="ORIGIN"):
        runner.remote_url(url)


@pytest.mark.parametrize("name", ["../outside", "/absolute", "a\\..\\x", "images/a?x"])
def test_zip_traversal(tmp_path: Path, name: str) -> None:
    """Unpack only registered local paths."""
    path = tmp_path / "result.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, b"bad")
    with pytest.raises(common.ExperimentError):
        runner.extract_zip(path, tmp_path / "result")
    assert not (tmp_path / "result").exists()


def test_seal_missing_changed_and_extra(tmp_path: Path) -> None:
    """Every mutation of the original result set is visible."""
    (tmp_path / "data").write_text("x")
    common.seal(tmp_path)
    common.verify(tmp_path)
    (tmp_path / "extra").write_text("x")
    with pytest.raises(common.ExperimentError, match="EVIDENCE_HASH"):
        common.verify(tmp_path)


def test_offline_and_partial_macro() -> None:
    """A partial source set never becomes a complete four-document macro average."""
    with common.offline(), pytest.raises(common.ExperimentError, match="NETWORK_DISABLED"):
        socket.socket()
    summary = {
        "rows": [
            {
                "arm": "A",
                "group": "G1",
                "owner_cer_records": [{"distance": 1, "reference_chars": 10}],
            }
        ]
    }
    metric = report.aggregate(summary)["A"]["owner"]
    assert metric["represented_source_count"] == 1
    assert not metric["complete_four_source_macro"]


def test_pending_resume_never_posts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Polling a saved task at deadline does not submit or upload anything."""
    common.write(
        tmp_path / "receipt.json", {"group": "G1", "data_id": "test", "status": "PENDING_REMOTE"}
    )
    common.write(tmp_path / "remote-state.json", {"batch_id": "batch"})
    calls = []

    def api(*args: Any, **kwargs: Any) -> common.Json:
        calls.append(args[2])
        return {"data": {"extract_result": [{"data_id": "test", "state": "running"}]}}

    monkeypatch.setattr(runner, "api_call", api)
    result = runner.collect(tmp_path, "synthetic", timeout=0)
    assert calls == ["GET"]
    assert result["status"] == "PENDING_REMOTE"


def test_existing_run_cannot_submit_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """O_EXCL-style admission blocks repeat parse before any credentials are read."""
    folder = tmp_path / "runs/G1/B"
    folder.mkdir(parents=True)
    common.write(folder / "receipt.json", {"status": "FAILED"})
    monkeypatch.setattr(runner, "frozen", lambda _: {"groups": {"G1": {}}})
    with pytest.raises(FileExistsError):
        runner.execute(tmp_path, "B", "G1", None)
    assert not (tmp_path / "active.lock").exists()


def test_invalid_docx_is_not_success() -> None:
    """A downloaded file with the correct extension is insufficient."""
    with pytest.raises(common.ExperimentError, match="DOCX_INVALID"):
        common.inspect_docx(b"not a document")


def test_lossless_selection_and_physical_map(tmp_path: Path) -> None:
    """Selection preserves source-page geometry and exact rendered pixels."""
    pdf = prepare.pdfium.PdfDocument.new()
    for size in [(100, 120), (200, 240), (300, 360)]:
        page = pdf.new_page(*size)
        page.close()
    source = tmp_path / "source.pdf"
    pdf.save(source)
    pdf.close()
    before = common.digest(source)
    mapping = prepare.subset(source, [3, 1], tmp_path / "subset.pdf", tmp_path / "images")
    assert [r["original_page"] for r in mapping] == [3, 1]
    assert [r["size_pt"] for r in mapping] == [[300, 360], [100, 120]]
    assert common.digest(source) == before


def test_source_binding_failure_before_converter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wrong reference/source binding cannot reach a model or converter."""
    monkeypatch.setattr(prepare, "ROOT", tmp_path)
    dataset = tmp_path / "dataset"
    common.write(dataset / "manifest.v7.json", {"samples": []})
    common.write(dataset / "edit.json", {"source_binding": ["wrong"], "base_manifest_version": 7})
    with pytest.raises(common.ExperimentError, match="REVIEW_SOURCE_BINDING"):
        prepare.prepare(dataset, dataset / "edit.json", tmp_path / "tmp/docx-demo/test")


def test_api_token_stays_on_api_client_request(tmp_path: Path) -> None:
    """Authorization is per API request, never a client default inherited by storage."""
    requests = []

    def handle(request: runner.httpx.Request) -> runner.httpx.Response:
        requests.append(request)
        return runner.httpx.Response(200, json={"code": 0, "data": {}})

    with runner.httpx.Client(transport=runner.httpx.MockTransport(handle)) as client:
        runner.api_call(
            client, tmp_path, "GET", "/extract-results/batch/test", "private-test-token"
        )
        client.get("https://cdn-mineru.openxlab.org.cn/result.zip")
    assert requests[0].headers["Authorization"] == "Bearer private-test-token"
    assert "Authorization" not in requests[1].headers
    assert "private-test-token" not in (tmp_path / "http.jsonl").read_text()


def test_paired_metric_uses_identical_reference_set(tmp_path: Path) -> None:
    """Unequal alignment coverage cannot be compared as if it shared a denominator."""
    from experiments.recognition_compare.analysis import comparison

    frozen = tmp_path / "frozen"
    frozen.mkdir()
    common.seal(frozen)
    evaluation = tmp_path / "evaluation"
    for arm, ids in [("B", ["shared", "B-only"]), ("C", ["shared"])]:
        matches = [
            {
                "reference": {"id": key, "kind": "text", "human_confirmed": False},
                "status": "MATCHED",
                "cer": {"distance": 1, "reference_chars": 10},
            }
            for key in ids
        ]
        common.write(
            evaluation / "G1" / f"{arm}-scoring.json",
            {
                "pages": [
                    {
                        "original_page": 2,
                        "aggregate_content": True,
                        "matches": matches,
                        "reading_order_edges": [],
                        "discarded": [],
                        "unmatched_outputs": [],
                        "actual_route": "NOT_PROVIDED",
                        "expected_route": "scan",
                    }
                ]
            },
        )
    result = comparison(tmp_path, evaluation, tmp_path / "analysis")
    pair = next(p for p in result["paired_text"] if p["left"] == "B" and not p["owner_confirmed"])
    assert pair["common_unit_count"] == 1
    assert pair["sources"]["mix"]["reference_chars"] == 10
    assert pair["left_total_scorable_units"] == 2
