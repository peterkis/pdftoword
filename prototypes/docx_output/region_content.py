"""Source-bounded normalization for region-only fallback, leaving raw responses immutable."""

from __future__ import annotations

import copy
import math
import re

from .common import Json, box_valid
from .structure import chat_content


def normalize_region_content(responses: Json, size: list[int]) -> tuple[Json, list[Json]]:
    """Preserve one uniquely located unsupported HTML table as an image, not the page."""
    content = chat_content(responses["ovis"])
    tables = list(re.finditer(r"<table\b[^>]*>.*?</table\s*>", content, re.I | re.S))
    # Multiple tables require a structural association algorithm, not ordinal guessing.
    if len(tables) != 1 or len(re.findall(r"<table\b", content, re.I)) != 1:
        return responses, []
    raw = responses.get("pp", {}).get("result", {}).get("layoutParsingResults", [])
    if not raw:
        return responses, []
    raw = raw[0]["prunedResult"]
    if [raw.get("width"), raw.get("height")] != size:
        return responses, []
    boxes = [
        r["block_bbox"] for r in raw.get("parsing_res_list", []) if r["block_label"] == "table"
    ]
    if len(boxes) != 1 or not box_valid(boxes[0]):
        return responses, []
    x0, y0, x1, y1 = boxes[0]
    width, height = size
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        return responses, []
    coords = [
        math.floor(x0 / width * 1000),
        math.floor(y0 / height * 1000),
        math.ceil(x1 / width * 1000),
        math.ceil(y1 / height * 1000),
    ]
    tag = '<img src="images/bbox_' + "_".join(map(str, coords)) + '.jpg" />'
    match = tables[0]
    normalized = copy.deepcopy(responses)
    normalized["ovis"]["choices"][0]["message"]["content"] = (
        content[: match.start()] + "\n\n" + tag + "\n\n" + content[match.end() :]
    )
    return normalized, [
        {
            "tag": tag,
            "source_span": [match.start(), match.end()],
            "raw_markup": match[0],
            "bbox_px": boxes[0],
            "reason": "REGION_TABLE_FALLBACK",
        }
    ]
