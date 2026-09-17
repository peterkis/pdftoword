"""Import supplementary annotations without executing package code or overwriting data."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import re
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any

from product_dataset import ROOT, inside, read, sha256, validate_dataset, write


def adapt_annotation(
    source: dict[str, Any],
    item: dict[str, Any],
    version: int,
    *,
    human_reviewer: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Preserve source anchors and content; uncertain or unsupported facts remain unscored."""
    sid = item["sample_id"]
    if (
        source["sample_id"] != sid
        or source["source"]["sha256"] != item["source_sha256"]
        or source["source"]["selected_pages"] != item["selected_pages"]
        or [p["page"] for p in source["pages"]] != item["selected_pages"]
    ):
        raise ValueError("IDENTITY_MISMATCH")
    result: dict[str, Any] = {
        "schema_version": "product-annotation/1.0",
        "annotation_version": version,
        "sample_id": sid,
        "source_sha256": item["source_sha256"],
        "reviewer_type": "human" if human_reviewer else "agent_visual",
        "reviewer_id": human_reviewer or "imported-agent-visual",
        "coverage_complete": bool(
            human_reviewer
            and source["agent_coverage_complete"]
            and all(p["agent_coverage_complete"] for p in source["pages"])
        ),
        "anchors": [],
        "units": [],
    }
    stats: dict[str, Any] = {
        "source_reviewer_type": source["reviewer_type"],
        "blocks": 0,
        "tables": 0,
        "cells": 0,
        "empty_cells": 0,
        "formulas": 0,
        "unsupported_relations": 0,
    }

    def add(page: int, kind: str, key: str, reference: dict[str, Any], confirmed: bool) -> None:
        result["units"].append(
            {
                "unit_id": uuid.uuid5(uuid.UUID(sid), f"{page}:{kind}:{key}").hex,
                "page": page,
                "kind": kind,
                "status": "confirmed" if confirmed else "uncertain",
                "reference": reference,
                "note": "Source evidence and original structure retained in import archive.",
            }
        )

    for page in source["pages"]:
        number = page["page"]
        for anchor in page["anchors"]:
            original = anchor["kind"]
            kind = (
                original
                if original in {"figure", "question", "caption", "table", "formula"}
                else "question"
                if original in {"question_prompt", "question_instruction"}
                else "text"
            )
            result["anchors"].append(
                {"id": anchor["id"], "page": number, "kind": kind, "bbox": anchor["bbox"]}
            )
        add(number, "route", "page", {"route": page["route"]}, True)
        for block in page["blocks"]:
            stats["blocks"] += 1
            text = block["text"]
            certain = (
                block["evidence_status"] == "agent_confirmed"
                and "[uncertain:" not in text
                and bool(text.strip())
            )
            add(
                number,
                "text",
                block["anchor_id"],
                {
                    "text": text,
                    "source_anchor_id": block["anchor_id"],
                    "source_kind": block["kind"],
                    "content_scope": (
                        "marginal"
                        if block["kind"] in {"header", "footer"}
                        else "figure_text"
                        if block["kind"] == "figure_text"
                        else "body"
                    ),
                },
                certain,
            )
        for table in page["tables"]:
            stats["tables"] += 1
            cells = []
            for cell in table["cells"]:
                stats["cells"] += 1
                stats["empty_cells"] += not bool(cell["text"])
                cells.append({k: cell[k] for k in ("row", "col", "rowspan", "colspan", "text")})
                cells[-1]["source_anchor_id"] = cell["anchor_id"]
            add(
                number,
                "table",
                table["anchor_id"],
                {
                    "rows": table["rows"],
                    "cols": table["columns"],
                    "cells": cells,
                    "source_anchor_id": table["anchor_id"],
                    "subtype": table["subtype"],
                    "is_data_table": table["is_data_table"],
                },
                all(
                    c["evidence_status"] == "agent_confirmed" and "[uncertain:" not in c["text"]
                    for c in table["cells"]
                ),
            )
            result["units"][-1]["reference"].update(
                {
                    key: copy.deepcopy(table[key])
                    for key in (
                        "logical_table_id",
                        "segment_index",
                        "segment_count",
                        "logical_data_row_numbers",
                        "logical_table_total_data_rows",
                        "header_is_repeated",
                        "header_rows",
                        "cell_reading_order",
                    )
                    if key in table
                }
            )
        for formula in page["formulas"]:
            stats["formulas"] += 1
            text = formula["source_expression"]
            add(
                number,
                "formula",
                formula["anchor_id"],
                {
                    "text": text,
                    "source_anchor_id": formula["anchor_id"],
                    "source_subtype": formula["subtype"],
                },
                formula["evidence_status"] == "agent_confirmed" and "[uncertain:" not in text,
            )
        if len(page["reading_order"]) >= 2:
            add(
                number,
                "reading_order",
                "body",
                {"anchors": page["reading_order"], "scope": "body"},
                True,
            )
        for relation in page["relationships"]:
            source_kind = relation["relation"]
            mapped = {
                "caption_of": "caption_of",
                "references_figure": "references",
                "belongs_to_question": "belongs_to",
            }.get(source_kind)
            anchor_roles = {a["id"]: a["kind"] for a in result["anchors"]}
            expected = {
                "caption_of": ("caption", "figure"),
                "references": ("question", "figure"),
                "belongs_to": ("figure", "question"),
            }.get(mapped or "")
            actual = tuple(
                anchor_roles.get(relation[k]) for k in ("from_anchor_id", "to_anchor_id")
            )
            if mapped is not None and actual != expected:
                mapped = None
            # Preserve all other relation types, but do not score them with a different meaning.
            if mapped is None:
                stats["unsupported_relations"] += 1
            add(
                number,
                "figure_edge",
                relation["id"],
                {
                    "from": relation["from_anchor_id"],
                    "to": relation["to_anchor_id"],
                    "relation": mapped or source_kind,
                    "source_relation": source_kind,
                },
                mapped is not None and relation["evidence_status"] == "agent_confirmed",
            )
    return result, stats


def apply_owner_readings(
    annotation: dict[str, Any], readings: dict[str, str]
) -> tuple[dict[str, Any], list[str]]:
    """Replace only explicit uncertainty tokens using subsequently confirmed literal readings."""
    result = copy.deepcopy(annotation)
    applied = []
    for unit in result["units"]:
        if unit["kind"] != "text":
            continue
        text = unit["reference"].get("text")
        if not isinstance(text, str):
            continue
        changed = False
        for key, reading in readings.items():
            tokens = ("[uncertain:" + key + "]", "⟦" + key + "⟧")
            if any(token in text for token in tokens):
                if not isinstance(reading, str) or not reading.strip():
                    raise ValueError("EMPTY_HUMAN_READING")
                for token in tokens:
                    text = text.replace(token, reading)
                applied.append(key)
                changed = True
        if changed:
            unit["reference"]["text"] = text
            unit["status"] = "uncertain" if "[uncertain:" in text or "⟦U-" in text else "confirmed"
            unit["note"] += " Explicit subsequent user reading recorded; previous version retained."
    return result, applied


def exclude_owner_confirmed_noise(annotation: dict[str, Any], anchor_id: str) -> dict[str, Any]:
    """Exclude confirmed scan noise from text/order, retaining its source record."""
    result = copy.deepcopy(annotation)
    anchor = next(a for a in result["anchors"] if a["id"] == anchor_id)
    excluded = [
        u
        for u in result["units"]
        if u["kind"] == "text" and u["reference"].get("source_anchor_id") == anchor_id
    ]
    if len(excluded) != 1:
        raise ValueError("NOISE_ANCHOR_AMBIGUOUS")
    result["units"] = [u for u in result["units"] if u not in excluded]
    result["anchors"] = [a for a in result["anchors"] if a["id"] != anchor_id]
    for unit in result["units"]:
        if unit["kind"] == "reading_order":
            unit["reference"]["anchors"] = [
                a for a in unit["reference"]["anchors"] if a != anchor_id
            ]
        if unit["kind"] == "route" and unit["page"] == anchor["page"]:
            unit["reference"].setdefault("owner_confirmed_non_content", []).append(
                {
                    "source_anchor": anchor,
                    "original_unit": excluded[0],
                    "decision": "scan_noise",
                }
            )
    result["units"] = [
        u
        for u in result["units"]
        if not (u["kind"] == "reading_order" and len(u["reference"]["anchors"]) < 2)
    ]
    return result


def verify_column_spans(table: dict[str, Any], expected: dict[int, list[tuple[int, int]]]) -> None:
    """Verify explicit owner-provided vertical spans, including header and final singleton rows."""
    if set(expected) != set(range(table["cols"])) or any(c["colspan"] != 1 for c in table["cells"]):
        raise ValueError("COLUMN_SPAN_SCOPE_MISMATCH")
    for col, spans in expected.items():
        actual = sorted((c["row"], c["rowspan"]) for c in table["cells"] if c["col"] == col)
        if actual != sorted(spans):
            raise ValueError("OWNER_SPAN_MISMATCH")


def merge_source_events(data: dict[str, Any], source: dict[str, Any]) -> int:
    """Merge original holdout exposure with its original time; other source events stay archived."""
    by_id = {item["sample_id"]: item for item in data["items"]}
    existing = {event["event_id"] for event in data["events"]}
    added = 0
    for event in source.get("events", []):
        if event.get("type") not in {
            "holdout_viewed_for_annotation",
            "split_unknown_viewed_for_annotation",
        }:
            continue
        sid = event["sample_id"]
        if (
            event["type"] == "split_unknown_viewed_for_annotation"
            and sid in by_id
            and by_id[sid]["split"] != "holdout"
        ):
            continue
        if sid not in by_id or by_id[sid]["split"] != "holdout":
            raise ValueError("SOURCE_HOLDOUT_EVENT_MISMATCH")
        eid = uuid.uuid5(uuid.UUID(data["dataset_id"]), json.dumps(event, sort_keys=True)).hex
        if eid not in existing:
            data["events"].append(
                {
                    "event_id": eid,
                    "sample_id": sid,
                    "action": "holdout_access",
                    "actor": "source-package-agent-visual",
                    "timestamp": event.get("timestamp") or event["at"],
                    "reason": "Original annotation access; full attachment exposure recorded; "
                    "no converter tuning. Source event retained in archive.",
                }
            )
            existing.add(eid)
            added += 1
    return added


def verified_package(package: Path) -> dict[str, str]:
    """Validate declared file hashes and reject paths escaping the supplied package."""
    entries = {}
    for line in (package / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        if name in entries or sha256(inside(package, name)) != digest:
            raise ValueError("PACKAGE_HASH_MISMATCH")
        entries[name] = digest
    if not entries:
        raise ValueError("PACKAGE_EMPTY")
    return entries


def archive_package(package: Path, destination: Path, hashes: dict[str, str]) -> None:
    """Retain complete source bytes in ZIP; do not expand Python into repository scanners."""
    with zipfile.ZipFile(destination / "source-package.zip", "x", zipfile.ZIP_DEFLATED) as archive:
        for name, expected in hashes.items():
            source = inside(package, name)
            if sha256(source) != expected:
                raise ValueError("IMPORT_COPY_HASH_MISMATCH")
            archive.write(source, name)
            if Path(name).suffix not in {".py", ".pyi"}:
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copyfile(source, target)
                target.chmod(0o600)
                if sha256(target) != expected:
                    raise ValueError("IMPORT_COPY_HASH_MISMATCH")
    (destination / "source-package.zip").chmod(0o600)


def next_version(directory: Path, prefix: str) -> int:
    """Choose an unused version without mutating earlier revisions."""
    versions = [
        int(m.group(1))
        for p in directory.glob(prefix + "*.json")
        if (m := re.fullmatch(re.escape(prefix) + r"(\d+)\.json", p.name))
    ]
    return max(versions, default=0) + 1


def integrate(
    manifest: Path,
    package: Path,
    *,
    owner_confirmed: bool,
    human_reviewer: str | None,
    package_manifest: str = "manifest.v5.json",
) -> dict[str, Any]:
    """Merge only matching supplementary samples into a new full manifest and private archive."""
    if not manifest.resolve().is_relative_to(ROOT / "tmp/productization"):
        raise ValueError("PRIVATE_ROOT_REQUIRED")
    hashes = verified_package(package)
    if package_manifest not in hashes:
        raise ValueError("UNSEALED_MANIFEST")
    source_manifest = read(inside(package, package_manifest))
    data = copy.deepcopy(read(manifest))
    by_id = {item["sample_id"]: item for item in data["items"]}
    prepared = []
    for sample in source_manifest["samples"]:
        item = by_id[sample["sample_id"]]
        if sample["split"] is not None and sample["split"] != item["split"]:
            raise ValueError("SPLIT_MISMATCH")
        if sample["annotation_path"] not in hashes:
            raise ValueError("UNSEALED_ANNOTATION")
        annotation = read(inside(package, sample["annotation_path"]))
        uploaded = inside(package.parent, annotation["source"]["uploaded_filename"])
        if sha256(uploaded) != item["source_sha256"]:
            raise ValueError("UPLOADED_PDF_HASH_MISMATCH")
        version = next_version(manifest.parent / "annotations", item["sample_id"] + ".v")
        adapted, stats = adapt_annotation(annotation, item, version, human_reviewer=human_reviewer)
        prepared.append((item, adapted, stats))
    merge_source_events(data, source_manifest)
    root = manifest.parent
    revision = next_version(root, "manifest.v")
    archive = root / "imports" / ("review-" + uuid.uuid4().hex)
    archive.mkdir(parents=True, mode=0o700)
    archive_package(package, archive, hashes)
    shutil.copyfile(package / "SHA256SUMS.txt", archive / "SHA256SUMS.txt")
    now = dt.datetime.now(dt.UTC).isoformat()
    for item in data["items"]:
        if owner_confirmed:
            old_family = item["document_family"]
            # Same declared original hash remains grouped, even after owner confirmation.
            item["document_family"] = uuid.uuid5(
                uuid.UUID(data["dataset_id"]), item["original_sha256"]
            ).hex
            item["family_review"] = "CONFIRMED"
            item["participated_in_tuning"] = False
            data["events"].append(
                {
                    "event_id": uuid.uuid4().hex,
                    "sample_id": item["sample_id"],
                    "action": "reassign",
                    "actor": "user-session-2026-09-16",
                    "timestamp": now,
                    "reason": "User confirms independent originals and no prior tuning; "
                    "previous family " + old_family + " retained in prior manifest.",
                }
            )
    mapping = []
    for item, adapted, stats in prepared:
        name = item["sample_id"] + f".v{adapted['annotation_version']}.json"
        write(root / "annotations" / name, adapted)
        item["annotation_path"] = name
        item["reviewer_type"] = adapted["reviewer_type"]
        item["annotation_status"] = "REVIEWED_HUMAN" if adapted["coverage_complete"] else "PARTIAL"
        actions = ["human_review"] if human_reviewer else []
        if item["split"] == "holdout":
            actions.append("holdout_access")
        for action in actions:
            data["events"].append(
                {
                    "event_id": uuid.uuid4().hex,
                    "sample_id": item["sample_id"],
                    "action": action,
                    "actor": human_reviewer or "annotation-import",
                    "timestamp": now,
                    "reason": "Supplementary selected-page review; "
                    "user confirmation recorded separately from source agent origin; "
                    "uncertainties preserved; no conversion tuning.",
                }
            )
        mapping.append({"sample_id": item["sample_id"], "annotation_path": name, **stats})
    data["revision"] = revision
    data["status"] = "DRAFT"
    target = root / f"manifest.v{revision}.json"
    write(target, data)
    write(
        archive / "integration.json",
        {
            "source_manifest_sha256": sha256(manifest),
            "package_file_hashes": hashes,
            "target_manifest_sha256": sha256(target),
            "owner_confirmation": owner_confirmed,
            "human_confirmation": human_reviewer,
            "mapping": mapping,
            "note": "Archive source stays agent_visual; human confirmation is subsequent.",
        },
    )
    result = validate_dataset(target)
    return {
        "manifest_revision": revision,
        "imported_samples": len(mapping),
        "mapping_counts": [
            {k: v for k, v in x.items() if k not in {"sample_id", "annotation_path"}}
            for x in mapping
        ],
        "dataset": result,
    }


def main() -> int:
    """Require explicit confirmation flags; never infer human acceptance from file names."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--owner-confirmed-independent-unused", action="store_true")
    parser.add_argument("--human-reviewer")
    parser.add_argument("--package-manifest", default="manifest.v5.json")
    args = parser.parse_args()
    try:
        result = integrate(
            args.manifest,
            args.package,
            owner_confirmed=args.owner_confirmed_independent_unused,
            human_reviewer=args.human_reviewer,
            package_manifest=args.package_manifest,
        )
        print(json.dumps(result, ensure_ascii=False))
        return (
            0
            if result["dataset"]["status"] == "READY"
            else 2
            if result["dataset"]["status"] == "INVALID"
            else 3
        )
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"status": "INVALID", "errors": ["REVIEW_IMPORT_REJECTED"]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
