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


def _unexpected_layout_grid(
    observed: Json,
    truth: Json,
    bound: dict[str, list[int]],
    owned: set[int],
    fallback_ids: list[str],
) -> bool:
    """Validate explicit layout grids or the writer's borderless flow wrapper shape."""
    covered: set[int] = set()
    paragraphs = observed["paragraphs"]

    def shape(value: Json) -> Any:
        return (
            value["rows"],
            value["cols"],
            sorted((c["row"], c["col"], c["rowspan"], c["colspan"]) for c in value["cells"]),
        )

    for unit in truth["units"]:
        if unit["kind"] != "table" or not isinstance(unit.get("reference"), dict):
            continue
        reference = unit["reference"]
        tables = {
            paragraphs[i]["table"] for i in bound.get(reference.get("source_anchor_id", ""), [])
        } - {None}
        if unit["status"] != "confirmed":
            covered.update(tables)  # Unknown topology stays review-required, never PASS.
        elif reference.get("is_data_table", True):
            if unit["unit_id"] not in fallback_ids:
                covered.update(tables)  # Already checked as actual data-table topology.
        elif tables:
            if len(tables) != 1 or shape(observed["tables"][next(iter(tables))]) != shape(
                reference
            ):
                return True
            covered.update(tables)
    for table_id in owned - covered:
        table = observed["tables"][table_id]
        cells = sorted(table["cells"], key=lambda c: (c["row"], c["col"]))
        coordinates = [(row, col) for row in range(table["rows"]) for col in range(table["cols"])]
        if (
            not table["borderless"]
            or [(c["row"], c["col"]) for c in cells] != coordinates
            or any(c["rowspan"] != 1 or c["colspan"] != 1 for c in cells)
        ):
            return True
        filled = [bool(c["has_content"]) for c in cells]
        if not any(filled):
            return True
        last_filled = max(i for i, filled_cell in enumerate(filled) if filled_cell)
        trailing = len(filled) - last_filled - 1
        if (
            not all(filled[: last_filled + 1])
            or trailing >= table["cols"]
            or (table["rows"] == 1 and trailing)
        ):
            return True
    return False


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
    uncertain_units = [
        u
        for u in truth["units"]
        if u["status"] != "confirmed" and u["kind"] in {"text", "formula", "table"}
    ]
    unscored_math_nodes: set[tuple[int, int]] = set()
    for uncertain in uncertain_units:
        reference = uncertain.get("reference")
        if not isinstance(reference, dict):
            continue
        uncertain_indexes = set(bound.get(reference.get("source_anchor_id", ""), []))
        if uncertain["kind"] == "table":
            uncertain_tables = {paragraphs[i]["table"] for i in uncertain_indexes} - {None}
            uncertain_indexes.update(
                i for i, p in enumerate(paragraphs) if p["table"] in uncertain_tables
            )
        if uncertain["kind"] in {"text", "table"}:
            claimed.update(uncertain_indexes)
        if uncertain["kind"] == "table":
            unscored_math_nodes.update(
                (i, j) for i in uncertain_indexes for j in range(len(paragraphs[i]["math"]))
            )
    confirmed = [u for u in truth["units"] if u["status"] == "confirmed"]
    text_anchors = {u["reference"]["source_anchor_id"] for u in confirmed if u["kind"] == "text"}
    units = []
    for unit in confirmed:
        ref = unit["reference"]
        if unit["kind"] == "table" and ref.get("is_data_table") is False:
            aid = ref["source_anchor_id"]
            layout_indexes = bound.get(aid, [])
            layout_tables = {paragraphs[i]["table"] for i in layout_indexes} - {None}
            bound[aid] = sorted(
                set(layout_indexes)
                | {i for i, p in enumerate(paragraphs) if p["table"] in layout_tables}
            )
            if aid not in text_anchors:
                units.append(
                    {
                        **unit,
                        "kind": "text",
                        "reference": {
                            "source_anchor_id": aid,
                            "text": "".join(
                                c["text"]
                                for c in sorted(ref["cells"], key=lambda c: (c["row"], c["col"]))
                            ),
                            "content_scope": "body",
                        },
                    }
                )
        else:
            units.append(unit)
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
    boxes_by_page: dict[int, list[list[float]]] = {}
    preserved_anchors: set[str] = set()
    claimed_image_paragraphs: set[int] = set()
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
            claimed_image_paragraphs.add(drawing[0])
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
    image_preserved_unit_ids = {
        u["unit_id"] for u in units if u["reference"].get("source_anchor_id") in preserved_anchors
    }
    from .structure import score_structure

    structures, structure_failures, table_claimed = score_structure(
        observed,
        units,
        bound,
        block_anchor,
        sources,
        unscored_math_nodes=unscored_math_nodes,
        image_preserved_unit_ids=image_preserved_unit_ids,
        uncertain_formulas=[u for u in uncertain_units if u["kind"] == "formula"],
        uncertain_edges=[
            u for u in truth["units"] if u["status"] != "confirmed" and u["kind"] == "figure_edge"
        ],
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
    owned_tables = {paragraphs[i]["table"] for i in claimed | claimed_image_paragraphs} - {None}
    if _unexpected_layout_grid(
        observed, truth, bound, owned_tables, structures["tables"]["fallback_unit_ids"]
    ):
        errors.append("UNEXPECTED_LAYOUT_GRID")
    unclaimed_tables = set(range(len(observed["tables"]))) - owned_tables
    metrics["tables"]["unclaimed_output_count"] = len(unclaimed_tables)
    if unclaimed_tables:
        errors.append("UNALIGNED_TABLE")
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
        if unit["unit_id"] in structures["formulas"]["present_unit_ids"]:
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
    metrics["necessary_content"]["uncertain_count"] = len(uncertain_units)
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
            f["unit_id"] not in preserved_units
            and f["code"]
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
    elif content_status != "FAIL" and (unsupported_present or uncertain_units):
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
    structural_metrics = [m for name, m in structures.items() if name != "table_editable"]
    scored_structures = [m for m in structural_metrics if m["scored_count"]]
    has_structural_fallback = (
        structures["tables"]["fallback_count"] or structures["formulas"]["fallback_count"]
    )
    editable_metrics = [
        text_metric["editable_coverage"],
        structures["table_editable"],
        structures["formulas"]["supported_coverage"],
    ]
    if any(m["status"] == "FAIL" for m in editable_metrics):
        result["editability_status"] = "FAIL"
    elif any(m["scored_count"] for m in editable_metrics):
        result["editability_status"] = (
            "REVIEW_REQUIRED"
            if uncertain_units or structures["formulas"]["unsupported_count"]
            else "PASS"
        )
    else:
        result["editability_status"] = "NOT_SCORED"
    if errors or structure_failures or any(m["status"] == "FAIL" for m in structural_metrics):
        result["structure_status"] = "FAIL"
    elif has_structural_fallback:
        result["structure_status"] = "REVIEW_REQUIRED"
    elif scored_structures:
        result["structure_status"] = (
            "REVIEW_REQUIRED"
            if any(m["not_scored_count"] or m["uncertain_count"] for m in structures.values())
            else "PASS"
        )
    result["semantic_sha256"] = semantic_hash(result)
    return result
