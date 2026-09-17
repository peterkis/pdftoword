"""Offline private corpus validation and immutable snapshots; never import conversion tools."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "specs/product-quality"
TARGETS = {"N": 6, "R": 6, "M": 4, "T": 4, "C": 4}
SPLITS = {"development": 12, "validation": 6, "holdout": 6}


def sha256(path: Path) -> str:
    """Hash bytes without interpreting or logging sensitive content."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Any:
    """Read private UTF-8 JSON; callers publish only safe classifications."""
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    """Exclusively write a private JSON file; never overwrite frozen evidence."""
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    path.chmod(0o600)


def inside(root: Path, relative: str) -> Path:
    """Only real, non-symlink files beneath the designated corpus/annotation root are allowed."""
    p = Path(relative)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        raise ValueError("PRIVATE_PATH_INVALID")
    target = root / p
    if any(x.is_symlink() for x in (target, *target.parents)):
        raise ValueError("PRIVATE_PATH_INVALID")
    if not target.resolve().is_relative_to(root.resolve()) or not target.is_file():
        raise ValueError("INPUT_MISSING")
    return target


def schema_errors(value: Any, name: str) -> bool:
    """Use the checked-in strict schemas with date-time validation, without remote refs."""
    schema = read(SPEC / name)
    return bool(
        list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
    )


def reference_valid(kind: str, value: dict[str, Any]) -> bool:
    """Reject empty confirmations and invalid topology; never normalize reference text."""
    if kind in {"text", "formula"}:
        text = value.get("text")
        if not isinstance(text, str):
            return False
        if kind == "formula":
            for wrapper in ("$$", "$", r"\(", r"\)", r"\[", r"\]"):
                text = text.replace(wrapper, "")
        return bool(text.strip())
    if kind == "route":
        return value.get("route") in {"native", "scan", "ordinary_figure", "mixed", "blank"}
    if kind == "reading_order":
        ids = value.get("anchors")
        return (
            isinstance(ids, list)
            and len(ids) >= 2
            and all(isinstance(x, str) and x.strip() for x in ids)
            and len(set(ids)) == len(ids)
        )
    if kind == "figure_edge":
        return (
            all(isinstance(value.get(k), str) and value[k].strip() for k in ("from", "to"))
            and value["from"] != value["to"]
            and value.get("relation") in {"belongs_to", "caption_of", "references"}
        )
    if kind == "table":
        rows, cols, cells = value.get("rows"), value.get("cols"), value.get("cells")
        if (
            type(rows) is not int
            or type(cols) is not int
            or rows < 1
            or cols < 1
            or not isinstance(cells, list)
            or not cells
        ):
            return False
        covered: set[tuple[int, int]] = set()
        for cell in cells:
            if not isinstance(cell, dict):
                return False
            r, c, rs, cs = (cell.get(k) for k in ("row", "col", "rowspan", "colspan"))
            if any(type(x) is not int for x in (r, c, rs, cs)) or not isinstance(
                cell.get("text"), str
            ):
                return False
            r, c, rs, cs = (cell[k] for k in ("row", "col", "rowspan", "colspan"))
            if r < 0 or c < 0 or rs < 1 or cs < 1 or r + rs > rows or c + cs > cols:
                return False
            locations = {(i, j) for i in range(r, r + rs) for j in range(c, c + cs)}
            if covered & locations:
                return False
            covered |= locations
        return len(covered) == rows * cols
    return False


def annotation_check(root: Path, item: dict[str, Any]) -> tuple[list[str], dict[str, int]]:
    """Keep agent and human annotations distinct and report denominators without accuracy scores."""
    errors = []
    counts = {"confirmed": 0, "uncertain": 0, "reference_characters": 0}
    if item["annotation_path"] is None:
        if item["annotation_status"] != "PENDING" or item["reviewer_type"] is not None:
            errors.append("ANNOTATION_STATE_MISMATCH")
        return errors, counts
    try:
        annotation = read(inside(root / "annotations", item["annotation_path"]))
        if schema_errors(annotation, "annotation.schema.json"):
            return ["ANNOTATION_SCHEMA_INVALID"], counts
        if (
            annotation["sample_id"] != item["sample_id"]
            or annotation["source_sha256"] != item["source_sha256"]
        ):
            errors.append("ANNOTATION_IDENTITY_MISMATCH")
        if item["annotation_status"] == "PENDING" or (
            item["annotation_status"] == "AGENT_VISUAL"
            and (
                annotation["reviewer_type"] != "agent_visual" or not annotation["coverage_complete"]
            )
        ):
            errors.append("ANNOTATION_STATE_MISMATCH")
        if not annotation["reviewer_id"].strip():
            errors.append("ANNOTATION_REVIEWER_MISSING")
        if item["reviewer_type"] != annotation["reviewer_type"]:
            errors.append("ANNOTATION_REVIEWER_MISMATCH")
        if item["annotation_status"] == "REVIEWED_HUMAN" and (
            annotation["reviewer_type"] != "human" or not annotation["coverage_complete"]
        ):
            errors.append("HUMAN_REVIEW_NOT_CONFIRMED")
        anchors = {a["id"]: a for a in annotation.get("anchors", [])}
        if len(anchors) != len(annotation.get("anchors", [])):
            errors.append("ANCHOR_ID_DUPLICATE")
        for anchor in anchors.values():
            bbox = anchor["bbox"]
            if anchor["page"] not in item["selected_pages"] or (
                bbox is not None and (bbox[2] <= bbox[0] or bbox[3] <= bbox[1])
            ):
                errors.append("ANCHOR_INVALID")
        ids = set()
        for unit in annotation["units"]:
            if unit["unit_id"] in ids or unit["page"] not in item["selected_pages"]:
                errors.append("ANNOTATION_UNIT_INVALID")
            ids.add(unit["unit_id"])
            counts[unit["status"]] += 1
            if unit["status"] == "confirmed":
                if not reference_valid(unit["kind"], unit["reference"]):
                    errors.append("CONFIRMED_REFERENCE_INVALID")
                elif unit["kind"] == "figure_edge":
                    ref = unit["reference"]
                    roles = {
                        "belongs_to": ("figure", "question"),
                        "caption_of": ("caption", "figure"),
                        "references": ("question", "figure"),
                    }
                    expected = roles.get(ref.get("relation"))
                    actual = tuple(anchors.get(ref.get(k), {}).get("kind") for k in ("from", "to"))
                    if actual != expected:
                        errors.append("FIGURE_EDGE_INVALID")
                elif unit["kind"] == "reading_order":
                    if any(a not in anchors for a in unit["reference"]["anchors"]):
                        errors.append("READING_ANCHOR_UNKNOWN")
                elif unit["kind"] == "text":
                    counts["reference_characters"] += len(unit["reference"]["text"])
        if annotation["coverage_complete"]:
            for selected_page in item["selected_pages"]:
                confirmed = [
                    u
                    for u in annotation["units"]
                    if u["page"] == selected_page and u["status"] == "confirmed"
                ]
                routes = [u["reference"].get("route") for u in confirmed if u["kind"] == "route"]
                if not routes or (
                    not any(r in {"blank", "ordinary_figure"} for r in routes)
                    and not any(u["kind"] in {"text", "formula", "table"} for u in confirmed)
                ):
                    errors.append("ANNOTATION_CONTENT_MISSING")
            if item["category"] == "T" and not any(
                u["kind"] == "table" and u["status"] == "confirmed" for u in annotation["units"]
            ):
                errors.append("TABLE_ANNOTATION_MISSING")
        if annotation["coverage_complete"] and (
            not annotation["units"]
            or set(item["selected_pages"]) != {u["page"] for u in annotation["units"]}
        ):
            errors.append("ANNOTATION_COVERAGE_INCOMPLETE")
    except (OSError, ValueError, TypeError):
        errors.append("ANNOTATION_UNAVAILABLE")
    return errors, counts


def validate_dataset(manifest: Path) -> dict[str, Any]:
    """Validate permission before reading sources; count independent real inputs only."""
    result: dict[str, Any] = {
        "status": "INVALID",
        "errors": [],
        "real_initial_documents": 0,
        "real_initial_pages": 0,
        "category_pages": dict.fromkeys(TARGETS, 0),
        "split_pages": dict.fromkeys(SPLITS, 0),
        "human_reviewed_categories": [],
        "metrics": {
            "status": "NOT_SCORED",
            "value": None,
            "confirmed": 0,
            "uncertain": 0,
            "reference_characters": 0,
            "scored_count": 0,
        },
    }
    errors = result["errors"]
    try:
        data = read(manifest)
        if schema_errors(data, "dataset-manifest.schema.json"):
            errors.append("MANIFEST_SCHEMA_INVALID")
            return result
        root = manifest.parent
        if data["status"] == "FROZEN":
            try:
                seal = read(root / "seal.json")
                names = {
                    p.relative_to(root).as_posix()
                    for p in root.rglob("*")
                    if p.is_file() and p != root / "seal.json"
                }
                if (
                    not isinstance(seal, dict)
                    or set(seal) != names
                    or any(sha256(inside(root, name)) != digest for name, digest in seal.items())
                ):
                    errors.append("FROZEN_SEAL_INVALID")
            except (OSError, ValueError):
                errors.append("FROZEN_SEAL_INVALID")
        legacy = set(read(SPEC / "development-only-sources.json")["sha256"])
        families: dict[str, str] = {}
        origins: dict[str, tuple[str, str]] = {}
        hashes: dict[str, tuple[str, str]] = {}
        ids: set[str] = set()
        initial_origins: set[str] = set()
        initial_families: set[str] = set()
        provenance_pending = False
        reviewed: set[str] = set()
        events = data["events"]
        for item in data["items"]:
            sid, family, split = item["sample_id"], item["document_family"], item["split"]
            provenance_pending |= (
                item["family_review"] != "CONFIRMED" or item["participated_in_tuning"] is None
            )
            if sid in ids:
                errors.append("DUPLICATE_SAMPLE_ID")
            ids.add(sid)
            if family in families and families[family] != split:
                errors.append("FAMILY_SPLIT_LEAKAGE")
            families[family] = split
            for mapping, key in (
                (origins, item["original_sha256"]),
                (hashes, item["source_sha256"]),
            ):
                if key in mapping and mapping[key] != (family, split):
                    errors.append("DERIVATIVE_GROUP_LEAKAGE")
                mapping[key] = (family, split)
            if (item["source_sha256"] in legacy or item["original_sha256"] in legacy) and (
                split != "development" or item["usage"] != "regression"
            ):
                errors.append("LEGACY_DEVELOPMENT_ONLY")
            if item["participated_in_tuning"] and split == "holdout":
                errors.append("HOLDOUT_TUNING_LEAKAGE")
            if item["participated_in_tuning"] and not any(
                e["sample_id"] == sid and e["action"] == "tuning" for e in events
            ):
                errors.append("TUNING_EVENT_MISSING")
            if any(e["sample_id"] == sid and e["action"] == "tuning" for e in events) and (
                not item["participated_in_tuning"] or split == "holdout"
            ):
                errors.append("HOLDOUT_TUNING_LEAKAGE")
            if item["model_send_authorized"] != bool(item["allowed_providers"]):
                errors.append("SEND_AUTHORIZATION_MISMATCH")
            pages = item["selected_pages"]
            if pages != list(range(min(pages), max(pages) + 1)):
                errors.append("NONCONTIGUOUS_PAGES")
            try:
                path = inside(root / "corpus", item["private_path"])
                if sha256(path) != item["source_sha256"]:
                    errors.append("SOURCE_HASH_MISMATCH")
                if item["input_type"] == "pdf":
                    with pdfium.PdfDocument(path) as pdf:
                        if max(pages) > len(pdf):
                            errors.append("PAGE_SELECTION_INVALID")
                else:
                    with Image.open(path) as image:
                        if image.format != {"jpg": "JPEG", "png": "PNG"}[item["input_type"]]:
                            errors.append("INPUT_TYPE_MISMATCH")
                        image.verify()
                    if pages != [1]:
                        errors.append("PAGE_SELECTION_INVALID")
            except (OSError, ValueError, pdfium.PdfiumError):
                errors.append("SOURCE_UNAVAILABLE")
            if (
                item["annotation_path"] is not None
                and split == "holdout"
                and not any(
                    e["sample_id"] == sid and e["action"] == "holdout_access" for e in events
                )
            ):
                errors.append("HOLDOUT_ACCESS_EVENT_MISSING")
            annotation_errors, counts = annotation_check(root, item)
            errors.extend(annotation_errors)
            if item["usage"] == "initial" and item["sensitivity"] != "synthetic":
                for key, count in counts.items():
                    result["metrics"][key] += count
            real = (
                item["sensitivity"] != "synthetic"
                and item["usage"] == "initial"
                and item["category"] in TARGETS
            )
            if real:
                if item["original_sha256"] in initial_origins:
                    errors.append("INITIAL_DOCUMENT_DUPLICATE")
                initial_origins.add(item["original_sha256"])
                initial_families.add(family)
                result["category_pages"][item["category"]] += len(pages)
                result["split_pages"][split] += len(pages)
                result["real_initial_pages"] += len(pages)
                if item["annotation_status"] == "REVIEWED_HUMAN" and not annotation_errors:
                    reviewed.add(item["category"])
        if any(e["sample_id"] not in ids for e in events):
            errors.append("EVENT_SAMPLE_UNKNOWN")
        if len({e["event_id"] for e in events}) != len(events):
            errors.append("EVENT_ID_DUPLICATE")
        result["metrics"]["eligible_count"] = result["metrics"]["confirmed"]
        result["metrics"]["not_scored_count"] = result["metrics"]["confirmed"]
        result["real_initial_documents"] = len(initial_families)
        result["real_initial_files"] = len(initial_origins)
        result["provenance_pending"] = provenance_pending
        result["human_reviewed_categories"] = sorted(reviewed)
        result["shortfalls"] = {
            k: max(0, v - result["category_pages"][k]) for k, v in TARGETS.items()
        }
        result["split_shortfalls"] = {
            k: max(0, v - result["split_pages"][k]) for k, v in SPLITS.items()
        }
        result["status"] = (
            "INVALID"
            if errors
            else "BLOCKED_INPUT"
            if (
                len(initial_families) < 12
                or any(result["shortfalls"].values())
                or any(result["split_shortfalls"].values())
            )
            else "BLOCKED_PROVENANCE"
            if provenance_pending
            else "BLOCKED_ANNOTATION"
            if set(reviewed) != set(TARGETS)
            or any(
                i["annotation_status"] in {"PENDING", "PARTIAL"}
                for i in data["items"]
                if i["usage"] == "initial"
            )
            else "READY"
        )
    except (OSError, ValueError, TypeError):
        errors.append("MANIFEST_UNAVAILABLE")
        result["status"] = "INVALID"
    return result


def freeze(manifest: Path, destination: Path) -> None:
    """Create a new sealed snapshot only after real corpus and annotation gates pass."""
    if validate_dataset(manifest)["status"] != "READY":
        raise ValueError("DATASET_NOT_READY")
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    data = read(manifest)
    for item in data["items"]:
        for folder, key in (("corpus", "private_path"), ("annotations", "annotation_path")):
            if item[key] is not None:
                target = destination / folder / item[key]
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copyfile(inside(manifest.parent / folder, item[key]), target)
                target.chmod(0o600)
    data["status"] = "FROZEN"
    write(destination / "manifest.json", data)
    write(
        destination / "seal.json",
        {
            p.relative_to(destination).as_posix(): sha256(p)
            for p in destination.rglob("*")
            if p.is_file()
        },
    )

    if validate_dataset(destination / "manifest.json")["status"] != "READY":
        raise ValueError("DATASET_CHANGED_DURING_FREEZE")


def main() -> int:
    """Initialize a private empty ledger or validate/freeze explicitly supplied local inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    init = subs.add_parser("init")
    init.add_argument("--root", type=Path, required=True)
    for name in ("validate", "freeze"):
        sub = subs.add_parser(name)
        sub.add_argument("--manifest", type=Path, required=True)
        if name == "freeze":
            sub.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = (
            args.root
            if args.command == "init"
            else args.output
            if args.command == "freeze"
            else None
        )
        if output is not None and (
            not output.resolve().is_relative_to(ROOT / "tmp/productization")
            or any(p.is_symlink() for p in (output, *output.parents))
        ):
            raise ValueError("OUTPUT_MUST_BE_PRIVATE")
        if args.command == "init":
            args.root.mkdir(parents=True, exist_ok=False, mode=0o700)
            for folder in ("corpus", "annotations"):
                (args.root / folder).mkdir(mode=0o700)
            manifest = args.root / "manifest.json"
            write(
                manifest,
                {
                    "schema_version": "product-dataset/1.1",
                    "dataset_id": uuid.uuid4().hex,
                    "revision": 1,
                    "status": "DRAFT",
                    "items": [],
                    "events": [],
                },
            )
        else:
            manifest = args.manifest
        result = validate_dataset(manifest)
        if args.command == "freeze" and result["status"] == "READY":
            freeze(manifest, args.output)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] == "READY" else 2 if result["status"] == "INVALID" else 3
    except (OSError, ValueError):
        print(json.dumps({"status": "INVALID", "errors": ["DATASET_OPERATION_REJECTED"]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
