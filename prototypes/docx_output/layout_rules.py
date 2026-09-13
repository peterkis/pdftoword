"""Versioned layout acceptance rules; these do not score OCR correctness."""

from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass
from statistics import median

from .common import DemoError, Json, area, box_valid, intersection, transform


@dataclass(frozen=True)
class LayoutRules:
    """Explicit, bounded rules for single-column exam-like layouts."""

    version: str = "layout-rules/1.0"
    vertical_overlap: float = 0.35
    minimum_figure_iou: float = 0.45
    ambiguity_ratio: float = 0.8
    wide_region_fraction: float = 0.35
    max_columns: int = 4
    label_max_width_pt: float = 40
    label_gap_pt: float = 30
    caption_gap_pt: float = 35

    def effective(self, boxes: list[list[float]]) -> Json:
        """Derive small tolerances from typical OCR line height in point units."""
        heights = [b[3] - b[1] for b in boxes if 6 <= b[3] - b[1] <= 30]
        line = median(heights) if heights else 16.0
        return {
            **asdict(self),
            "line_height_pt": line,
            "cell_gap_pt": min(10.0, max(6.0, line * 0.5)),
            "stem_tolerance_pt": min(8.0, max(4.0, line * 0.375)),
        }


RULES = LayoutRules()


def preflight(raw: Json, p: Json, info: Json) -> None:
    """Reject malformed, out-of-page, duplicate and multi-column geometry."""
    if [raw["width"], raw["height"]] != info["pixel_size"]:
        raise DemoError("COORDINATE_MAPPING_UNRESOLVED")
    sx, sy = info["pixel_to_point"]
    regions = raw["parsing_res_list"]
    boxes = []
    for r in regions:
        b = transform(r["block_bbox"], sx, sy)
        if not (0 <= b[0] < b[2] <= p["width_pt"] and 0 <= b[1] < b[3] <= p["height_pt"]):
            raise DemoError("PP_REGION_OUT_OF_PAGE")
        boxes.append((r["block_label"], b))
    for index, (label, a) in enumerate(boxes):
        for other, b in boxes[index + 1 :]:
            overlap = intersection(a, b)
            if label == other and overlap / (area(a) + area(b) - overlap) > 0.9:
                raise DemoError("DUPLICATE_PP_REGION")
            if label == other == "text" and min(a[2] - a[0], b[2] - b[0]) >= p["width_pt"] * 0.25:
                vertical = (min(a[3], b[3]) - max(a[1], b[1])) / min(a[3] - a[1], b[3] - b[1])
                gap = max(a[0], b[0]) - min(a[2], b[2])
                if vertical > 0.5 and gap > p["width_pt"] * 0.02:
                    raise DemoError("MULTICOLUMN_LAYOUT_REVIEW")
    ocr = raw.get("overall_ocr_res", {})
    angles = ocr.get("textline_orientation_angles", [])
    disabled = ocr.get("model_settings", {}).get("use_textline_orientation") is False
    # Frozen PP responses use -1 when the orientation module is disabled.
    if any(angle not in (None, 0) and not (disabled and angle == -1) for angle in angles):
        raise DemoError("ROTATED_TEXT_LAYOUT_REVIEW")


def accept_candidate(original: Json, candidate: Json, p: Json) -> None:
    """Prove preservation and check the display plan before committing geometry."""
    original_page = next(pg for pg in original["pages"] if pg["page_index"] == p["page_index"])
    if p["reading_order"] != original_page["reading_order"]:
        raise DemoError("READING_ORDER_CHANGED")
    before = [
        (b["id"], b["content"], b["content_candidates"])
        for b in original_page["blocks"]
        if b["content"]["kind"] == "text"
    ]
    after = [
        (b["id"], b["content"], b["content_candidates"])
        for b in p["blocks"]
        if b["content"]["kind"] == "text"
    ]
    if before != after or original["metadata"].get("inline_parts", {}) != candidate["metadata"].get(
        "inline_parts", {}
    ):
        raise DemoError("CONTENT_PRESERVATION_FAILED")
    if [b["id"] for b in original_page["blocks"] if b["type"] == "figure"] != [
        b["id"] for b in p["blocks"] if b["type"] == "figure"
    ]:
        raise DemoError("FIGURE_PRESERVATION_FAILED")
    fatal = {"LAYOUT_ALIGNMENT_REVIEW", "OPTION_LAYOUT_REVIEW", "FIGURE_GEOMETRY_ALIGNMENT_REVIEW"}
    if any(i["type"] in fatal and i["page_index"] == p["page_index"] for i in candidate["issues"]):
        raise DemoError("AMBIGUOUS_LAYOUT_MAPPING")
    if any(b["geometry_source"] != "pp_structure" for b in p["blocks"]):
        raise DemoError("INCOMPLETE_LAYOUT_MAPPING")
    questions = [b for b in p["blocks"] if b["type"] == "question"]
    for first, second in itertools.pairwise(questions):
        if first["bbox"][1] >= second["bbox"][1]:
            raise DemoError("NONMONOTONIC_QUESTION_MAPPING")
    by_id = {b["id"]: b for b in p["blocks"]}
    if len(by_id) != len(p["blocks"]) or set(p["reading_order"]) != set(by_id):
        raise DemoError("INVALID_BLOCK_COVERAGE")
    positions = {bid: i for i, bid in enumerate(p["reading_order"])}

    def contiguous(ids: list[str]) -> None:
        indices = sorted(positions[bid] for bid in ids)
        if indices and indices != list(range(indices[0], indices[-1] + 1)):
            raise DemoError("NONCONTIGUOUS_LAYOUT_GROUP")

    owned = set()
    for group in candidate["metadata"].get("text_groups", []):
        if group["page_index"] != p["page_index"]:
            continue
        if not 1 <= group["columns"] <= RULES.max_columns:
            raise DemoError("UNSUPPORTED_COLUMN_COUNT")
        contiguous([bid for row in group["rows"] for bid in row])
        for row in group["rows"]:
            if not row or len(row) > group["columns"]:
                raise DemoError("INVALID_LAYOUT_ROW")
            for bid in row:
                if bid not in by_id or bid in owned:
                    raise DemoError("DUPLICATE_OR_MISSING_PLACEMENT")
                owned.add(bid)
    for group in candidate["metadata"].get("figure_groups", []):
        if group["page_index"] != p["page_index"]:
            continue
        contiguous([bid for pair in group["pairs"] for bid in pair.values()])
        for pair in group["pairs"]:
            for bid in pair.values():
                if bid not in by_id or bid in owned:
                    raise DemoError("DUPLICATE_OR_MISSING_PLACEMENT")
                owned.add(bid)
    for b in p["blocks"]:
        if not box_valid(b["bbox"]):
            raise DemoError("INVALID_FINAL_GEOMETRY")
