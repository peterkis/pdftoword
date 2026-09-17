"""Corpus rules use isolated self-authored bytes and the actual validator."""

import hashlib
import json
from pathlib import Path

from PIL import Image

from product_dataset import validate_dataset


def case(root: Path) -> dict:
    (root / "corpus").mkdir(exist_ok=True)
    image = root / "corpus/source.png"
    Image.new("RGB", (32, 32), "white").save(image)
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    return {
        "schema_version": "product-dataset/1.1",
        "dataset_id": "a" * 32,
        "revision": 1,
        "status": "DRAFT",
        "events": [],
        "items": [
            {
                "sample_id": "b" * 32,
                "document_family": "c" * 32,
                "category": "N",
                "split": "development",
                "usage": "initial",
                "source_sha256": digest,
                "original_sha256": digest,
                "private_path": "source.png",
                "input_type": "png",
                "selected_pages": [1],
                "license_status": "CONFIRMED",
                "license_evidence": "Self-authored test image; not real corpus",
                "local_read_authorized": True,
                "sensitivity": "synthetic",
                "model_send_authorized": False,
                "allowed_providers": [],
                "participated_in_tuning": False,
                "family_review": "CONFIRMED",
                "annotation_status": "PENDING",
                "annotation_path": None,
                "reviewer_type": None,
            }
        ],
    }


def save(root: Path, data: dict) -> Path:
    p = root / "manifest.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_empty_dataset_is_blocked_not_success(tmp_path: Path) -> None:
    data = case(tmp_path)
    data["items"] = []
    result = validate_dataset(save(tmp_path, data))
    assert result["status"] == "BLOCKED_INPUT"
    assert result["real_initial_pages"] == 0
    assert result["metrics"]["value"] is None


def test_cross_split_family_is_rejected(tmp_path: Path) -> None:
    data = case(tmp_path)
    second = {**data["items"][0], "sample_id": "d" * 32, "split": "holdout"}
    data["items"].append(second)
    result = validate_dataset(save(tmp_path, data))
    assert "FAMILY_SPLIT_LEAKAGE" in result["errors"]


def test_missing_authorization_and_wrong_hash_are_rejected(tmp_path: Path) -> None:
    data = case(tmp_path)
    data["items"][0]["local_read_authorized"] = False
    assert validate_dataset(save(tmp_path, data))["errors"] == ["MANIFEST_SCHEMA_INVALID"]
    data["items"][0]["local_read_authorized"] = True
    data["items"][0]["source_sha256"] = "0" * 64
    assert "SOURCE_HASH_MISMATCH" in validate_dataset(save(tmp_path, data))["errors"]


def test_derivative_original_cannot_hide_in_another_family(tmp_path: Path) -> None:
    data = case(tmp_path)
    data["items"].append(
        {
            **data["items"][0],
            "sample_id": "d" * 32,
            "document_family": "e" * 32,
            "split": "validation",
        }
    )
    assert "DERIVATIVE_GROUP_LEAKAGE" in validate_dataset(save(tmp_path, data))["errors"]
    del data["items"][0]["original_sha256"]
    assert validate_dataset(save(tmp_path, data))["errors"] == ["MANIFEST_SCHEMA_INVALID"]


def test_empty_confirmed_and_fake_human_review_fail(tmp_path: Path) -> None:
    data = case(tmp_path)
    item = data["items"][0]
    item.update(
        annotation_path="v1.json", annotation_status="REVIEWED_HUMAN", reviewer_type="human"
    )
    (tmp_path / "annotations").mkdir()
    annotation = {
        "schema_version": "product-annotation/1.0",
        "annotation_version": 1,
        "sample_id": item["sample_id"],
        "source_sha256": item["source_sha256"],
        "reviewer_type": "agent_visual",
        "reviewer_id": "synthetic-agent",
        "coverage_complete": True,
        "anchors": [],
        "units": [
            {
                "unit_id": "e" * 32,
                "page": 1,
                "kind": "text",
                "status": "confirmed",
                "reference": {"text": "   "},
                "note": "",
            }
        ],
    }
    (tmp_path / "annotations/v1.json").write_text(json.dumps(annotation))
    errors = validate_dataset(save(tmp_path, data))["errors"]
    assert "CONFIRMED_REFERENCE_INVALID" in errors
    assert "HUMAN_REVIEW_NOT_CONFIRMED" in errors


def test_legacy_source_cannot_enter_new_holdout(tmp_path: Path) -> None:
    data = case(tmp_path)
    data["items"][0]["original_sha256"] = (
        "fe608629ae8af60890684c77437b3d62facd3a0c27b9fa019692890f96cbcf52"
    )
    data["items"][0]["split"] = "holdout"
    assert "LEGACY_DEVELOPMENT_ONLY" in validate_dataset(save(tmp_path, data))["errors"]


def test_frozen_manifest_without_seal_is_rejected(tmp_path: Path) -> None:
    data = case(tmp_path)
    data["status"] = "FROZEN"
    assert "FROZEN_SEAL_INVALID" in validate_dataset(save(tmp_path, data))["errors"]


def complete_fixture(root: Path) -> Path:
    """Fabricate a complete manifest for validator tests, never a real/human corpus claim."""
    import uuid

    from tests.demo.synthetic import make_pdf

    data = case(root)
    template = data["items"][0]
    data["items"] = []
    (root / "annotations").mkdir()
    for index, category in enumerate("NNNRRRMMTTCC"):
        sid = uuid.uuid4().hex
        source = root / "corpus" / f"{sid}.pdf"
        make_pdf(source, pages=2, decoration=f"% fixture {index}".encode())
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        split = "development" if index < 6 else "validation" if index < 9 else "holdout"
        item = {
            **template,
            "sample_id": sid,
            "document_family": uuid.uuid4().hex,
            "category": category,
            "source_sha256": digest,
            "original_sha256": digest,
            "private_path": source.name,
            "input_type": "pdf",
            "selected_pages": [1, 2],
            "split": split,
            "sensitivity": "public",
            "annotation_path": sid + ".json",
            "annotation_status": "REVIEWED_HUMAN",
            "reviewer_type": "human",
        }
        units = []
        for page in [1, 2]:
            for kind, reference in [
                ("route", {"route": "native"}),
                ("text", {"text": "synthetic fixture"}),
            ]:
                units.append(
                    {
                        "unit_id": uuid.uuid4().hex,
                        "page": page,
                        "kind": kind,
                        "status": "confirmed",
                        "reference": reference,
                        "note": "test only",
                    }
                )
        if category == "T":
            units.append(
                {
                    "unit_id": uuid.uuid4().hex,
                    "page": 1,
                    "kind": "table",
                    "status": "confirmed",
                    "reference": {
                        "rows": 1,
                        "cols": 1,
                        "cells": [
                            {"row": 0, "col": 0, "rowspan": 1, "colspan": 1, "text": "fixture"}
                        ],
                    },
                    "note": "test only",
                }
            )
        annotation = {
            "schema_version": "product-annotation/1.0",
            "annotation_version": 1,
            "sample_id": sid,
            "source_sha256": digest,
            "reviewer_type": "human",
            "reviewer_id": "synthetic-not-a-real-human-review",
            "coverage_complete": True,
            "anchors": [],
            "units": units,
        }
        (root / "annotations" / item["annotation_path"]).write_text(json.dumps(annotation))
        data["items"].append(item)
        if split == "holdout":
            data["events"].append(
                {
                    "event_id": uuid.uuid4().hex,
                    "sample_id": sid,
                    "action": "holdout_access",
                    "actor": "fixture",
                    "timestamp": "2026-09-15T00:00:00Z",
                    "reason": "test fixture only",
                }
            )
    return save(root, data)


def test_freeze_rejects_overwrite_and_detects_tampering(tmp_path: Path) -> None:
    import pytest

    from product_dataset import freeze

    root = tmp_path / "draft"
    root.mkdir()
    manifest = complete_fixture(root)
    assert validate_dataset(manifest)["status"] == "READY"
    destination = tmp_path / "frozen"
    freeze(manifest, destination)
    assert validate_dataset(destination / "manifest.json")["status"] == "READY"
    with pytest.raises(FileExistsError):
        freeze(manifest, destination)
    data = json.loads((destination / "manifest.json").read_text())
    path = destination / "annotations" / data["items"][0]["annotation_path"]
    path.write_text("{}")
    assert "FROZEN_SEAL_INVALID" in validate_dataset(destination / "manifest.json")["errors"]


def test_holdout_tuning_and_invented_figure_anchor_fail(tmp_path: Path) -> None:
    manifest = complete_fixture(tmp_path)
    data = json.loads(manifest.read_text())
    item = data["items"][-1]
    item["participated_in_tuning"] = True
    ann = tmp_path / "annotations" / item["annotation_path"]
    annotation = json.loads(ann.read_text())
    annotation["units"][1].update(
        kind="figure_edge",
        reference={"from": "unknown", "to": "unknown-question", "relation": "belongs_to"},
    )
    ann.write_text(json.dumps(annotation))
    errors = validate_dataset(save(tmp_path, data))["errors"]
    assert "HOLDOUT_TUNING_LEAKAGE" in errors
    assert "FIGURE_EDGE_INVALID" in errors


def test_summary_never_contains_private_paths_or_reference_text(tmp_path: Path) -> None:
    manifest = complete_fixture(tmp_path)
    result = validate_dataset(manifest)
    rendered = json.dumps(result)
    assert str(tmp_path) not in rendered
    assert "synthetic fixture" not in rendered
    assert "private_path" not in rendered
    assert result["metrics"]["value"] is None
    assert result["metrics"]["scored_count"] == 0


def test_incomplete_corpus_cannot_be_frozen(tmp_path: Path) -> None:
    import pytest

    from product_dataset import freeze

    manifest = save(tmp_path, case(tmp_path))
    with pytest.raises(ValueError, match="DATASET_NOT_READY"):
        freeze(manifest, tmp_path / "not-created")
    assert not (tmp_path / "not-created").exists()


def test_hash_matched_but_unreadable_pdf_is_safe_failure(tmp_path: Path) -> None:
    data = case(tmp_path)
    source = tmp_path / "corpus/source.pdf"
    source.write_bytes(b"%PDF-broken")
    data["items"][0].update(
        input_type="pdf",
        private_path="source.pdf",
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    assert "SOURCE_UNAVAILABLE" in validate_dataset(save(tmp_path, data))["errors"]


def test_cli_preserves_blocked_state_and_does_not_create_snapshot(tmp_path: Path) -> None:
    import subprocess
    import sys
    import uuid

    from product_dataset import ROOT

    manifest = save(tmp_path, case(tmp_path))
    output = ROOT / "tmp/productization" / ("blocked-probe-" + uuid.uuid4().hex)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/product_dataset.py"),
            "freeze",
            "--manifest",
            str(manifest),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 3
    assert json.loads(result.stdout)["status"] == "BLOCKED_INPUT"
    assert not output.exists()
