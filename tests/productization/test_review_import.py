"""Review imports preserve provenance and reject changed source identity."""

from pathlib import Path
from typing import Any

import pytest

from import_review_annotations import adapt_annotation


def source() -> tuple[dict, dict]:
    sid = "a" * 32
    aid = "b" * 32
    item = {"sample_id": sid, "source_sha256": "c" * 64, "selected_pages": [25]}
    data = {
        "sample_id": sid,
        "source": {"sha256": "c" * 64, "selected_pages": [25]},
        "reviewer_type": "agent_visual",
        "agent_coverage_complete": True,
        "pages": [
            {
                "page": 25,
                "route": "native",
                "agent_coverage_complete": True,
                "anchors": [{"id": aid, "page": 25, "kind": "paragraph", "bbox": [1, 2, 30, 40]}],
                "blocks": [
                    {
                        "anchor_id": aid,
                        "kind": "paragraph",
                        "text": "Known [uncertain:U-1]",
                        "evidence_status": "uncertain",
                    }
                ],
                "tables": [],
                "formulas": [],
                "relationships": [],
                "reading_order": [aid],
            }
        ],
    }
    return data, item


def test_uncertain_tokens_never_become_confirmed_text() -> None:
    data, item = source()
    result, stats = adapt_annotation(data, item, 4, human_reviewer="user-confirmed")
    text = next(u for u in result["units"] if u["kind"] == "text")
    assert text["status"] == "uncertain"
    assert "[uncertain:U-1]" in text["reference"]["text"]
    assert result["reviewer_type"] == "human"
    assert stats["source_reviewer_type"] == "agent_visual"


def test_user_confirmation_is_not_inferred_from_source_coverage() -> None:
    data, item = source()
    result, _ = adapt_annotation(data, item, 4, human_reviewer=None)
    assert result["reviewer_type"] == "agent_visual"
    assert result["coverage_complete"] is False


@pytest.mark.parametrize("change", ["hash", "page"])
def test_changed_source_or_page_mapping_is_rejected(change: str) -> None:
    data, item = source()
    if change == "hash":
        data["source"]["sha256"] = "0" * 64
    else:
        data["pages"][0]["page"] = 1
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        adapt_annotation(data, item, 4, human_reviewer=None)


def test_empty_exercise_cells_and_unsupported_relations_are_preserved() -> None:
    data, item = source()
    page = data["pages"][0]
    anchor = "b" * 32
    page["tables"] = [
        {
            "anchor_id": "d" * 32,
            "rows": 1,
            "columns": 1,
            "subtype": "exercise_response_grid",
            "is_data_table": False,
            "cells": [
                {
                    "anchor_id": "e" * 32,
                    "row": 0,
                    "col": 0,
                    "rowspan": 1,
                    "colspan": 1,
                    "text": "",
                    "evidence_status": "agent_confirmed",
                }
            ],
        }
    ]
    page["relationships"] = [
        {
            "id": "f" * 32,
            "from_anchor_id": anchor,
            "to_anchor_id": "d" * 32,
            "relation": "references_table",
            "evidence_status": "agent_confirmed",
        }
    ]
    result, stats = adapt_annotation(data, item, 4, human_reviewer="user-confirmed")
    table = next(u["reference"] for u in result["units"] if u["kind"] == "table")
    assert table["cells"][0]["text"] == ""
    assert table["is_data_table"] is False
    relation = next(u for u in result["units"] if u["kind"] == "figure_edge")
    assert relation["status"] == "uncertain"
    assert relation["reference"]["source_relation"] == "references_table"
    assert stats["empty_cells"] == 1


def test_package_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    from import_review_annotations import verified_package

    (tmp_path / "source.json").write_text("{}")
    (tmp_path / "SHA256SUMS.txt").write_text("0" * 64 + "  source.json\n")
    with pytest.raises(ValueError, match="PACKAGE_HASH_MISMATCH"):
        verified_package(tmp_path)


def test_package_python_is_preserved_in_zip_not_expanded(tmp_path: Path) -> None:
    import hashlib
    import zipfile

    from import_review_annotations import archive_package

    package = tmp_path / "source"
    package.mkdir()
    output = tmp_path / "archive"
    output.mkdir()
    payload = b'raise AssertionError("must not execute")\n'
    (package / "helper.py").write_bytes(payload)
    (package / "data.json").write_text("{}")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in package.iterdir()}
    archive_package(package, output, hashes)
    assert not (output / "helper.py").exists()
    with zipfile.ZipFile(output / "source-package.zip") as archive:
        assert archive.read("helper.py") == payload
    assert (output / "data.json").read_text() == "{}"


def test_explicit_readings_update_only_target_tokens_and_preserve_old_version() -> None:
    from import_review_annotations import apply_owner_readings

    data, item = source()
    original, _ = adapt_annotation(data, item, 4, human_reviewer="user-confirmed")
    original["units"].append({"kind": "text", "reference": {}, "status": "uncertain"})
    result, applied = apply_owner_readings(original, {"U-1": "__"})
    new = next(u for u in result["units"] if u["kind"] == "text")
    old = next(u for u in original["units"] if u["kind"] == "text")
    assert applied == ["U-1"]
    assert new["reference"]["text"] == "Known __"
    assert new["status"] == "confirmed"
    assert old["status"] == "uncertain"
    assert "[uncertain:U-1]" in old["reference"]["text"]


def test_original_holdout_event_time_is_preserved_without_duplicate() -> None:
    from import_review_annotations import merge_source_events

    data: dict[str, Any] = {
        "dataset_id": "a" * 32,
        "items": [{"sample_id": "b" * 32, "split": "holdout"}],
        "events": [],
    }
    source = {
        "events": [
            {
                "type": "holdout_viewed_for_annotation",
                "sample_id": "b" * 32,
                "timestamp": "2026-09-15T08:10:23+00:00",
            }
        ]
    }
    assert merge_source_events(data, source) == 1
    assert merge_source_events(data, source) == 0
    assert data["events"][0]["timestamp"] == "2026-09-15T08:10:23+00:00"


def test_scan_noise_is_excluded_without_creating_empty_confirmed_text() -> None:
    from import_review_annotations import exclude_owner_confirmed_noise

    data, item = source()
    result, _ = adapt_annotation(data, item, 4, human_reviewer="owner")
    updated = exclude_owner_confirmed_noise(result, "b" * 32)
    assert not any(u["kind"] == "text" for u in updated["units"])
    route = next(u for u in updated["units"] if u["kind"] == "route")
    assert route["reference"]["owner_confirmed_non_content"][0]["decision"] == "scan_noise"
    assert any(u["kind"] == "text" for u in result["units"])


def test_declared_column_spans_are_verified_not_guessed() -> None:
    from import_review_annotations import verify_column_spans

    table = {
        "cols": 2,
        "cells": [
            {"row": 0, "col": 0, "rowspan": 3, "colspan": 1},
            *[{"row": i, "col": 1, "rowspan": 1, "colspan": 1} for i in range(3)],
        ],
    }
    verify_column_spans(table, {0: [(0, 3)], 1: [(0, 1), (1, 1), (2, 1)]})
    with pytest.raises(ValueError, match="OWNER_SPAN_MISMATCH"):
        verify_column_spans(table, {0: [(0, 2)], 1: [(0, 1), (1, 1), (2, 1)]})


def test_batch2_bracket_reading_and_unknown_split_event() -> None:
    from import_review_annotations import apply_owner_readings, merge_source_events

    data, item = source()
    a, _ = adapt_annotation(data, item, 4, human_reviewer="owner")
    text = next(u for u in a["units"] if u["kind"] == "text")
    text["reference"]["text"] = "North⟦U-C16-01⟧\nwood"
    b, applied = apply_owner_readings(a, {"U-C16-01": "-"})
    assert applied == ["U-C16-01"]
    assert next(u for u in b["units"] if u["kind"] == "text")["reference"]["text"] == "North-\nwood"
    manifest: dict[str, Any] = {
        "dataset_id": "a" * 32,
        "items": [{"sample_id": "b" * 32, "split": "holdout"}],
        "events": [],
    }
    assert (
        merge_source_events(
            manifest,
            {
                "events": [
                    {
                        "type": "split_unknown_viewed_for_annotation",
                        "sample_id": "b" * 32,
                        "at": "2026-09-16T00:00:00Z",
                    }
                ]
            },
        )
        == 1
    )
