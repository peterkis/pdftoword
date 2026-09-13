"""Geometry-only PP projection and bounded Ovis-to-layout association."""

from __future__ import annotations

import copy
from pathlib import Path

from .common import DemoError, Json, area, crop, intersection, issue, transform, union
from .layout_rules import RULES, accept_candidate, preflight


def rows_of(boxes: list[list[float]]) -> list[list[list[float]]]:
    """Group existing PP boxes by vertical overlap, without inspecting recognized text."""
    rows: list[list[list[float]]] = []
    for b in sorted(boxes, key=lambda x: (x[1], x[0])):
        match = next(
            (
                r
                for r in rows
                if (min(union(r)[3], b[3]) - max(union(r)[1], b[1]))
                / min(union(r)[3] - union(r)[1], b[3] - b[1])
                > RULES.vertical_overlap
            ),
            None,
        )
        if match is None:
            rows.append([b])
        else:
            match.append(b)
    return sorted(rows, key=lambda r: union(r)[1])


def cells_of(boxes: list[list[float]], gap_pt: float = 8.0) -> list[list[float]]:
    """Merge touching label/formula fragments into geometry cells."""
    cells: list[list[float]] = []
    for b in sorted(boxes, key=lambda x: x[0]):
        if cells and b[0] - cells[-1][2] <= gap_pt:
            cells[-1] = union([cells[-1], b])
        else:
            cells.append(b)
    return cells


def _apply_pp_layout(job: Path, ir: Json, p: Json, body: Json, request_id: str) -> None:
    """Use only PP labels and boxes; never PP block_content/rec_texts/rec_formula."""
    raw = body["result"]["layoutParsingResults"][0]["prunedResult"]
    info = ir["provenance"]["pages"][str(p["page_index"])]
    if [raw["width"], raw["height"]] != info["pixel_size"] or raw.get("model_settings", {}).get(
        "use_doc_preprocessor"
    ):
        raise DemoError("COORDINATE_MAPPING_UNRESOLVED")
    preflight(raw, p, info)
    sx, sy = info["pixel_to_point"]
    regions = [
        {
            "id": f"pp-region-{n}",
            "label": r["block_label"],
            "bbox": transform(r["block_bbox"], sx, sy),
        }
        for n, r in enumerate(raw["parsing_res_list"])
    ]
    fine = [transform(b, sx, sy) for b in raw.get("overall_ocr_res", {}).get("rec_boxes", [])]
    fine += [transform(f["dt_polys"], sx, sy) for f in raw.get("formula_res_list", [])]
    for bbox in fine:
        if not (
            0 <= bbox[0] < bbox[2] <= p["width_pt"] and 0 <= bbox[1] < bbox[3] <= p["height_pt"]
        ):
            raise DemoError("PP_FINE_REGION_OUT_OF_PAGE")
    policy = RULES.effective(fine)
    ir["metadata"]["layout_policy"] = policy
    ir["metadata"]["layout_provider"] = "pp"
    ir["metadata"]["layout_profile"] = "pp_geometry_flow"
    ir["provenance"].setdefault("pp_layout_only", {})[str(p["page_index"])] = {
        "request_id": request_id,
        "regions": regions,
        "fine_boxes": fine,
        "excluded_fields": ["block_content", "rec_texts", "rec_formula"],
        "alignment": "typed_sequence_and_geometry_only",
    }
    used: set[str] = set()
    blocks = p["blocks"]
    by_id = {b["id"]: b for b in blocks}

    def mark(b: Json, bbox: list[float], evidence: Json, approximate: bool = False) -> None:
        key = "pp-layout-" + b["id"]
        ir["provenance"][key] = {
            "request_id": request_id,
            **evidence,
            "bbox": bbox,
            "previous_bbox": b["bbox"],
            "approximate": approximate,
        }
        b["bbox"] = list(bbox)
        b["geometry_source"] = "pp_structure"
        b["provenance_refs"].append(key)
        b["flags"] = [f for f in b["flags"] if f != "text_geometry_unknown_full_page_reference"]
        if approximate:
            b["flags"].append("geometry_approximate_shared_row")

    figures = [r for r in regions if r["label"] in {"image", "chart"}]
    for b in (b for b in blocks if b["type"] == "figure"):
        edges = []
        for r in figures:
            if r["id"] not in used:
                overlap = intersection(b["bbox"], r["bbox"])
                edges.append((overlap / (area(b["bbox"]) + area(r["bbox"]) - overlap), r))
        edges.sort(key=lambda e: e[0], reverse=True)
        if (
            not edges
            or edges[0][0] < RULES.minimum_figure_iou
            or (len(edges) > 1 and edges[1][0] > RULES.ambiguity_ratio * edges[0][0])
        ):
            issue(
                ir,
                "FIGURE_GEOMETRY_ALIGNMENT_REVIEW",
                "Ovis图域与PP区域不能唯一关联，未强行替换。",
                [b["id"]],
                p["page_index"],
            )
            continue
        score, r = edges[0]
        used.add(r["id"])
        mark(
            b,
            r["bbox"],
            {"region_id": r["id"], "reason": "unique_overlap_with_Ovis_figure", "iou": score},
        )
        aid = crop(job, ir, p, b["bbox"], b["id"] + "-pp-figure")
        b["content"]["asset_id"] = aid
    for rel in ir["relations"]:
        if (
            rel["type"] not in {"label_of", "caption_of"}
            or rel["from"] not in by_id
            or rel["to"] not in by_id
        ):
            continue
        b, f = by_id[rel["from"]], by_id[rel["to"]]
        fb = f["bbox"]
        if rel["type"] == "label_of":
            candidates = [
                r
                for r in regions
                if r["label"] == "text"
                and r["id"] not in used
                and r["bbox"][2] - r["bbox"][0] < RULES.label_max_width_pt
                and 0 <= fb[0] - r["bbox"][2] < RULES.label_gap_pt
                and fb[1] <= r["bbox"][1] <= fb[3]
            ]
        else:
            candidates = [
                r
                for r in regions
                if r["label"] == "figure_title"
                and r["id"] not in used
                and 0 <= r["bbox"][1] - fb[3] < RULES.caption_gap_pt
                and fb[0] <= (r["bbox"][0] + r["bbox"][2]) / 2 <= fb[2]
            ]
        if len(candidates) == 1:
            r = candidates[0]
            used.add(r["id"])
            mark(b, r["bbox"], {"region_id": r["id"], "reason": "adjacent_figure_geometry"})
    for kind, label in [("heading", "doc_title"), ("footer", "number")]:
        targets = [b for b in blocks if b["type"] == kind]
        available = [r for r in regions if r["label"] == label]
        if len(targets) == len(available):
            for b, r in zip(targets, available, strict=True):
                mark(b, r["bbox"], {"region_id": r["id"], "reason": "matching_type_and_sequence"})
                used.add(r["id"])
    text_regions = [r for r in regions if r["label"] == "text" and r["id"] not in used]
    wide = [
        r
        for r in text_regions
        if r["bbox"][2] - r["bbox"][0] > RULES.wide_region_fraction * p["width_pt"]
    ]
    if not wide:
        issue(
            ir,
            "LAYOUT_ALIGNMENT_REVIEW",
            "没有足够的PP正文区域，保留Ovis流式顺序。",
            [],
            p["page_index"],
        )
        return
    left = min(r["bbox"][0] for r in wide)
    first_y = min(r["bbox"][1] for r in wide if r["bbox"][0] <= left + policy["stem_tolerance_pt"])
    prelude = sorted(
        [
            r
            for r in regions
            if r["label"] == "paragraph_title" or (r in text_regions and r["bbox"][1] < first_y)
        ],
        key=lambda r: r["bbox"][1],
    )
    target_prelude = []
    for b in blocks:
        if b["type"] == "question":
            break
        if b["type"] == "paragraph":
            target_prelude.append(b)
    if len(prelude) == len(target_prelude):
        for b, r in zip(target_prelude, prelude, strict=True):
            mark(b, r["bbox"], {"region_id": r["id"], "reason": "prelude_sequence"})
            used.add(r["id"])
    questions: list[Json] = []
    for r in text_regions:
        if r["id"] in used:
            continue
        owned = [box for box in fine if intersection(box, r["bbox"]) / area(box) > 0.5]
        rows = rows_of(owned) if owned else [[r["bbox"]]]
        if union(rows[0])[0] <= left + policy["stem_tolerance_pt"]:
            questions.append({"bbox": r["bbox"], "region_ids": [r["id"]], "options": []})
        else:
            for row in rows:
                bbox = union(row)
                if bbox[0] <= left + policy["stem_tolerance_pt"]:
                    questions.append({"bbox": bbox, "region_ids": [r["id"]], "options": []})
                elif questions:
                    questions[-1]["options"].append(
                        {
                            "bbox": bbox,
                            "cells": cells_of(row, policy["cell_gap_pt"]),
                            "region_id": r["id"],
                        }
                    )
    ovis_questions = [b for b in blocks if b["type"] == "question"]
    if len(questions) != len(ovis_questions):
        issue(
            ir,
            "LAYOUT_ALIGNMENT_REVIEW",
            "PP几何分组与Ovis题目数量不一致，不强行逐题映射。",
            [b["id"] for b in ovis_questions],
            p["page_index"],
        )
        return
    plans = ir["metadata"].setdefault("text_groups", [])
    for question, geometry in zip(ovis_questions, questions, strict=True):
        mark(
            question,
            geometry["bbox"],
            {"region_ids": geometry["region_ids"], "reason": "stem_indent_and_sequence"},
        )
        options = []
        for b in blocks[blocks.index(question) + 1 :]:
            if b["type"] == "question":
                break
            if b["type"] == "option" and b["geometry_source"] != "pp_structure":
                options.append(b)
        rows = geometry["options"]
        if not options or not rows:
            continue
        counts = [len(r["cells"]) for r in rows]
        exact = sum(counts) == len(options)
        if not exact:
            if len(options) % len(rows):
                issue(
                    ir,
                    "OPTION_LAYOUT_REVIEW",
                    "选项与PP行框无法可靠分配。",
                    [b["id"] for b in options],
                    p["page_index"],
                )
                continue
            counts = [len(options) // len(rows)] * len(rows)
        plan_rows = []
        cursor = 0
        for row, count in zip(rows, counts, strict=True):
            current = options[cursor : cursor + count]
            cursor += count
            for i, b in enumerate(current):
                mark(
                    b,
                    row["cells"][i] if exact else row["bbox"],
                    {"region_id": row["region_id"], "reason": "ordered_option_row_alignment"},
                    not exact,
                )
            plan_rows.append([b["id"] for b in current])
        plans.append(
            {
                "page_index": p["page_index"],
                "question_id": question["id"],
                "rows": plan_rows,
                "columns": max(counts),
                "indent_pt": max(0.0, rows[0]["bbox"][0] - left),
                "distribution_inferred": not exact,
            }
        )
    for group in ir["metadata"].get("figure_groups", []):
        if group["page_index"] != p["page_index"]:
            continue
        if group["kind"] == "option_grid":
            group["columns"] = len(group["pairs"])
            group["inline_labels"] = True
    ir["metadata"]["content_left_pt"] = left
    remaining = [
        b["id"] for b in blocks if "text_geometry_unknown_full_page_reference" in b["flags"]
    ]
    ir["issues"] = [
        i
        for i in ir["issues"]
        if i["type"] != "TEXT_GEOMETRY_NOT_PROVIDED" or i.get("page_index") != p["page_index"]
    ]
    if remaining:
        issue(
            ir, "TEXT_GEOMETRY_NOT_PROVIDED", "部分文字尚未匹配PP区域。", remaining, p["page_index"]
        )
    approximate = [b["id"] for b in blocks if "geometry_approximate_shared_row" in b["flags"]]
    if approximate:
        issue(
            ir,
            "SHARED_ROW_GEOMETRY",
            "PP将一行多个选项合成一个框；横排位置为布局推断，定位仍显示共享行。",
            approximate,
            p["page_index"],
        )
    ir["metrics"]["unlocated_text_block_count"] = len(remaining)
    p["routing_decision"] = "OVIS_CONTENT_PP_GEOMETRY"


def apply_pp_layout(job: Path, ir: Json, p: Json, body: Json, request_id: str) -> None:
    """Apply verified geometry atomically; retain the Ovis document on layout failure."""
    trial = copy.deepcopy(ir)
    trial_page = next(pg for pg in trial["pages"] if pg["page_index"] == p["page_index"])
    try:
        _apply_pp_layout(job, trial, trial_page, body, request_id)
        accept_candidate(ir, trial, trial_page)
    except (DemoError, KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        reason = str(exc) if isinstance(exc, DemoError) else "MALFORMED_PP_GEOMETRY"
        result = {
            "status": "FALLBACK",
            "rule_version": RULES.version,
            "reason": reason,
            "content_preserved": True,
            "fallback": "ovis_flow",
            "request_id": request_id,
        }
        record_validation(ir, p, result)
        ir["provenance"]["layout_rejection"] = result
        p["routing_decision"] = "LAYOUT_REVIEW_REQUIRED_OVIS_PRESERVED"
        issue(
            ir,
            "LAYOUT_RULES_FALLBACK",
            "布局未通过规则检查，保留Ovis内容与流式输出：" + reason,
            p["reading_order"],
            p["page_index"],
        )
        return
    result = {
        "status": "APPLIED",
        "rule_version": RULES.version,
        "effective_policy": trial["metadata"]["layout_policy"],
        "content_left_pt": trial["metadata"]["content_left_pt"],
        "content_preserved": True,
        "placement_validated": True,
        "ocr_accuracy": "NOT_EVALUATED_BY_LAYOUT_RULES",
    }
    record_validation(trial, trial_page, result)
    p.clear()
    p.update(trial_page)
    trial["pages"] = [p if pg["page_index"] == p["page_index"] else pg for pg in trial["pages"]]
    ir.clear()
    ir.update(trial)


def record_validation(ir: Json, p: Json, result: Json) -> None:
    """Retain per-page decisions and aggregate mixed layout outcomes."""
    pages = ir["metadata"].setdefault("layout_by_page", {})
    pages[str(p["page_index"])] = result
    statuses = {r["status"] for r in pages.values()}
    ir["metadata"]["layout_validation"] = {
        **result,
        "status": next(iter(statuses)) if len(statuses) == 1 else "PARTIAL",
        "pages": copy.deepcopy(pages),
    }
