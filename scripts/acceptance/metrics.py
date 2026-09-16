"""Frozen-reference metrics; no converter expected answers or QA character totals."""

from __future__ import annotations

import hashlib
import json
from itertools import pairwise
from pathlib import Path
from typing import Any

from .docx_reader import inspect
from .formula import reference_tree

Json = dict[str, Any]


def semantic_hash(value: Any) -> str:
    """Hash canonical scoring content, not run timing or DOCX ZIP timestamps."""
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def cer(reference: str, actual: str) -> Json:
    """Levenshtein S/D/I over Unicode codepoints; ties prefer substitution, deletion."""
    row = [(i, 0, 0, i) for i in range(len(actual) + 1)]
    for i, left in enumerate(reference, 1):
        new = [(i, 0, i, 0)]
        for j, right in enumerate(actual, 1):
            cost, sub, delete, insert = row[j - 1]
            candidates = [(cost + (left != right), sub + (left != right), delete, insert)]
            cost, sub, delete, insert = row[j]
            candidates.append((cost + 1, sub, delete + 1, insert))
            cost, sub, delete, insert = new[-1]
            candidates.append((cost + 1, sub, delete, insert + 1))
            new.append(min(candidates, key=lambda x: x[0]))
        row = new
    cost, sub, delete, insert = row[-1]
    return {
        "reference_chars": len(reference),
        "substitutions": sub,
        "deletions": delete,
        "insertions": insert,
        "distance": cost,
        "value": cost / len(reference) if reference else None,
    }


def metric(eligible: int, scored: int, correct: int, uncertain: int = 0) -> Json:
    """Retain empty and unscored denominators instead of treating them as perfect."""
    return {
        "eligible_count": eligible,
        "scored_count": scored,
        "correct_count": correct,
        "uncertain_count": uncertain,
        "not_scored_count": eligible - scored,
        "value": correct / eligible if eligible else None,
        "status": (
            "NOT_SCORED"
            if not scored
            else "FAIL"
            if correct < scored
            else "REVIEW_REQUIRED"
            if scored < eligible
            else "PASS"
        ),
    }


def union_area(boxes: list[list[float]]) -> float:
    """Exact axis-aligned rectangle union via vertical strips; never clip invalid boxes."""
    if any(len(b) != 4 or b[2] <= b[0] or b[3] <= b[1] for b in boxes):
        raise ValueError("INVALID_BBOX")
    xs = sorted({x for b in boxes for x in (b[0], b[2])})
    total = 0.0
    for left, right in pairwise(xs):
        intervals = sorted((b[1], b[3]) for b in boxes if b[0] < right and b[2] > left)
        top = bottom = 0.0
        height = 0.0
        for y0, y1 in intervals:
            if y0 > bottom:
                height += bottom - top
                top, bottom = y0, y1
            else:
                bottom = max(bottom, y1)
        total += (right - left) * (height + bottom - top)
    return total


def _has_math_content(tree: Any) -> bool:
    """Empty OMML containers do not establish preserved formula content."""
    return bool(tree[1].strip()) or any(_has_math_content(child) for child in tree[2])


def evaluate(docx: Path, truth: Json, sources: Json) -> Json:
    """Evaluate actual editable output against frozen units using geometric provenance."""
    observed = inspect(docx)
    errors = list(observed["errors"])
    paragraphs = observed["paragraphs"]
    anchor_map = {a["id"]: a for a in truth["anchors"]}
    bound: dict[str, list[int]] = {a: [] for a in anchor_map}
    block_anchor: dict[str, str] = {}
    marker_blocks = {b["marker"]: b for b in sources["blocks"]}
    claimed: set[int] = set()
    for marker, block in marker_blocks.items():
        found = [i for i, p in enumerate(paragraphs) if marker in p["markers"]]
        if len(found) > 1:
            errors.append("DUPLICATE_SOURCE_BLOCK")
        box = block["bbox"]
        candidates = []
        area = (box[2] - box[0]) * (box[3] - box[1])
        for aid, anchor in anchor_map.items():
            if anchor["page"] != block["page"] or area <= 0:
                continue
            a = anchor["bbox"]
            overlap = max(0, min(a[2], box[2]) - max(a[0], box[0])) * max(
                0, min(a[3], box[3]) - max(a[1], box[1])
            )
            anchor_area = (a[2] - a[0]) * (a[3] - a[1])
            if min(area, anchor_area) > 0 and overlap / min(area, anchor_area) >= 0.5:
                candidates.append((overlap / min(area, anchor_area), aid))
        if candidates:
            if len(candidates) == 1:
                block_anchor[block["block_id"]] = candidates[0][1]
            for _, aid in candidates:
                bound[aid].extend(found)
    units = [u for u in truth["units"] if u["status"] == "confirmed"]
    structural_anchors = {
        u["reference"].get("source_anchor_id") for u in units if u["kind"] in {"table", "formula"}
    }
    text_units = [
        u
        for u in units
        if u["kind"] == "text"
        and u["reference"].get("content_scope") != "figure_text"
        and u["reference"].get("source_anchor_id") not in structural_anchors
    ]
    faithful_unit_ids: set[str] = set()
    totals: dict[str, Json] = {
        name: {
            "reference_chars": 0,
            "substitutions": 0,
            "deletions": 0,
            "insertions": 0,
            "distance": 0,
        }
        for name in ("raw", "light", "matched")
    }
    text_correct = faithful_chars = present = 0
    failures: list[Json] = []
    # Connected groups handle one paragraph spanning several independently annotated lines.
    # A physical paragraph contributes once; grouping uses geometry, never reference text.
    groups: list[tuple[list[Json], set[int]]] = []
    for unit in text_units:
        indexes = set(bound.get(unit["reference"]["source_anchor_id"], []))
        matching = [g for g in groups if g[1] & indexes]
        merged_units = [unit]
        for group in matching:
            merged_units.extend(group[0])
            indexes.update(group[1])
            groups.remove(group)
        groups.append((merged_units, indexes))
    for group_units, indexes in groups:
        claimed.update(indexes)
        group_units.sort(
            key=lambda u: (
                u["page"],
                anchor_map[u["reference"]["source_anchor_id"]]["bbox"][1],
                anchor_map[u["reference"]["source_anchor_id"]]["bbox"][0],
            )
        )
        ref = "".join(u["reference"]["text"] for u in group_units)
        actual = "".join(paragraphs[i]["text"] for i in sorted(indexes))
        exact = ref == actual
        text_correct += len(group_units) if exact else 0
        if exact:
            faithful_unit_ids.update(u["unit_id"] for u in group_units)
        faithful_chars += len(ref) if exact else 0
        present += sum(
            bool(u["reference"]["text"]) and u["reference"]["text"] in actual for u in group_units
        )
        for name, left, right in [
            ("raw", ref, actual),
            ("light", "".join(ref.split()), "".join(actual.split())),
            ("matched", ref if indexes else "", actual if indexes else ""),
        ]:
            values = cer(left, right)
            for key in totals[name]:
                totals[name][key] += values[key]
        if not exact:
            for u in group_units:
                failures.append(
                    {
                        "unit_id": u["unit_id"],
                        "page": u["page"],
                        "code": "TEXT_MISMATCH" if actual else "MISSING_TEXT",
                    }
                )
    for values in totals.values():
        values["value"] = (
            values["distance"] / values["reference_chars"] if values["reference_chars"] else None
        )
    text_metric = metric(
        len(text_units),
        len(text_units),
        text_correct,
        sum(u["kind"] == "text" and u["status"] != "confirmed" for u in truth["units"]),
    )
    text_metric.update(totals)
    text_metric["snippet_presence"] = metric(len(text_units), len(text_units), present)
    text_metric["editable_coverage"] = metric(
        totals["raw"]["reference_chars"], totals["raw"]["reference_chars"], faithful_chars
    )
    text_metric["excluded_figure_text_units"] = sum(
        u["kind"] == "text" and u["reference"].get("content_scope") == "figure_text" for u in units
    )
    text_metric["excluded_structural_overlap_units"] = sum(
        u["kind"] == "text" and u["reference"].get("source_anchor_id") in structural_anchors
        for u in units
    )
    metrics: Json = {"text": text_metric}
    from .structure import score_structure

    structures, structure_failures, table_claimed = score_structure(
        observed,
        units,
        bound,
        block_anchor,
        sources,
        complete_relations=(
            truth.get("coverage_complete") is True
            and not any(
                u["kind"] == "figure_edge" and u["status"] != "confirmed" for u in truth["units"]
            )
        ),
    )
    metrics.update(structures)
    if structures["formulas"]["unmatched_output_count"]:
        errors.append("UNALIGNED_FORMULA")
    failures.extend(structure_failures)
    claimed.update(table_claimed)
    extra_text = "".join(p["text"] for i, p in enumerate(paragraphs) if i not in claimed)
    if extra_text:
        errors.append("UNALIGNED_EDITABLE_TEXT")
        for name, extra in [("raw", extra_text), ("light", "".join(extra_text.split()))]:
            totals[name]["insertions"] += len(extra)
            totals[name]["distance"] += len(extra)
            denominator = totals[name]["reference_chars"]
            totals[name]["value"] = totals[name]["distance"] / denominator if denominator else None
        text_metric["status"] = "FAIL"
    page_metrics = []
    for page in sources["pages"]:
        expected = [u for u in text_units if u["page"] == page["page"]]
        matched = sum(bool(bound.get(u["reference"]["source_anchor_id"])) for u in expected)
        page_metrics.append({"page": page["page"], **metric(len(expected), len(expected), matched)})
    metrics["pages"] = page_metrics
    boxes_by_page: dict[int, list[list[float]]] = {}
    preserved_anchors: set[str] = set()
    unclaimed_images = {
        (i, j) for i, paragraph in enumerate(paragraphs) for j in range(len(paragraph["images"]))
    }
    for block in sources["blocks"]:
        image_indexes = [i for i, p in enumerate(paragraphs) if block["marker"] in p["markers"]]
        for image in block.get("images", []):
            drawing = next(
                (
                    (i, j)
                    for i in image_indexes
                    for j, actual_hash in enumerate(paragraphs[i]["images"])
                    if actual_hash == image["sha256"] and (i, j) in unclaimed_images
                ),
                None,
            )
            if drawing is None:
                errors.append("MISSING_OR_REPLACED_IMAGE")
                continue
            unclaimed_images.remove(drawing)
            if image["fallback"]:
                boxes_by_page.setdefault(block["page"], []).append(image["bbox"])
            box = image["bbox"]
            for aid, anchor in anchor_map.items():
                a = anchor["bbox"]
                if anchor["page"] == block["page"] and (
                    box[0] <= a[0] and box[1] <= a[1] and box[2] >= a[2] and box[3] >= a[3]
                ):
                    preserved_anchors.add(aid)
        # Legacy/minimal synthetic provenance can only report declared fallback area.
        if block.get("fallback") and "images" not in block:
            boxes_by_page.setdefault(block["page"], []).append(block["bbox"])
    if unclaimed_images:
        errors.append("UNALIGNED_IMAGE")
    total_area = sum(p["width"] * p["height"] for p in sources["pages"])
    fallback_area = 0.0
    for page in sources["pages"]:
        boxes = boxes_by_page.get(page["page"], [])
        if any(
            b[0] < 0 or b[1] < 0 or b[2] > page["width"] or b[3] > page["height"] for b in boxes
        ):
            errors.append("OUT_OF_BOUNDS_FALLBACK")
        else:
            fallback_area += union_area(boxes)
    metrics["fallback_area"] = {
        "source_area_pt2": total_area,
        "union_area_pt2": fallback_area,
        "value": fallback_area / total_area if total_area else None,
        "basis": "source_provenance_not_visual_crop_acceptance",
    }
    content_units = [u for u in units if u["kind"] in {"text", "formula", "table"}]
    content_failures = {f["unit_id"] for f in failures}
    supported_formula_ids = {
        u["unit_id"]
        for u in content_units
        if u["kind"] == "formula" and reference_tree(u["reference"]["text"]) is not None
    }
    correct_units = {
        u["unit_id"]
        for u in content_units
        if (u["kind"] == "text" and u["unit_id"] in faithful_unit_ids)
        or (
            u["kind"] == "formula"
            and u["unit_id"] in supported_formula_ids
            and u["unit_id"] not in content_failures
        )
        or (
            u["kind"] == "table"
            and u["reference"].get("is_data_table", True)
            and u["unit_id"] not in content_failures
        )
    }
    preserved_units = {
        u["unit_id"]
        for u in content_units
        if u["reference"].get("source_anchor_id") in preserved_anchors
    }
    unsupported_present: set[str] = set()
    for unit in content_units:
        if unit["kind"] != "formula" or unit["unit_id"] in supported_formula_ids:
            continue
        if unit["unit_id"] in preserved_units:
            continue
        formula_indexes = bound.get(unit["reference"]["source_anchor_id"], [])
        if any(_has_math_content(m) for i in formula_indexes for m in paragraphs[i]["math"]):
            unsupported_present.add(unit["unit_id"])
        else:
            failures.append(
                {"unit_id": unit["unit_id"], "page": unit["page"], "code": "MISSING_FORMULA"}
            )
    metrics["necessary_content"] = metric(
        len(content_units),
        len(content_units) - len(unsupported_present),
        len(correct_units | preserved_units),
    )
    metrics["necessary_content"]["source_image_retained_count"] = len(preserved_units)
    metrics["necessary_content"]["visual_crop_acceptance"] = "PENDING"
    if preserved_units and metrics["necessary_content"]["status"] == "PASS":
        metrics["necessary_content"]["status"] = "REVIEW_REQUIRED"
    # Structural claims are independent of ordinary paragraph character counts.
    for name, kind in {
        "tables": "table",
        "formulas": "formula",
        "relation_coverage": "figure_edge",
        "reading_order": "reading_order",
    }.items():
        metrics[name]["uncertain_count"] = sum(
            u["kind"] == kind and u["status"] != "confirmed" for u in truth["units"]
        )
    content_status = metrics["necessary_content"]["status"]
    if (
        any(
            f["code"]
            in {
                "TEXT_MISMATCH",
                "MISSING_TEXT",
                "TABLE_MISMATCH",
                "FORMULA_MISMATCH",
                "MISSING_FORMULA",
            }
            for f in failures
        )
        or extra_text
    ):
        content_status = "FAIL"
    elif content_status != "FAIL" and unsupported_present:
        content_status = "REVIEW_REQUIRED"
    result: Json = {
        "schema_version": "product-result/1.0",
        "execution_status": "COMPLETE",
        "content_status": content_status,
        "structure_status": "NOT_SCORED",
        "editability_status": text_metric["editable_coverage"]["status"],
        "rendering_status": "PENDING",
        "human_acceptance": "PENDING",
        "metrics": metrics,
        "failures": failures,
        "errors": sorted(set(errors)),
    }
    scored_structures = [m for m in structures.values() if m["scored_count"]]
    if errors or structure_failures or any(m["status"] == "FAIL" for m in structures.values()):
        result["structure_status"] = "FAIL"
    elif scored_structures:
        result["structure_status"] = (
            "REVIEW_REQUIRED" if any(m["not_scored_count"] for m in structures.values()) else "PASS"
        )
    result["semantic_sha256"] = semantic_hash(result)
    return result
