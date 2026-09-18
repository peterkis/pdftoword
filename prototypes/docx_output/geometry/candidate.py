"""Bounded geometry records and explicit crop/resize/pad coordinate transforms."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from ..common import Json

MAX_REGIONS = 10000


def numbers(value: Any, count: int) -> list[float]:
    """Require finite numeric coordinates without coercing strings or booleans."""
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise ValueError("INVALID_COORDINATES")
    try:
        if any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            for v in value
        ):
            raise ValueError("INVALID_COORDINATES")
        return [float(v) for v in value]
    except OverflowError:
        raise ValueError("INVALID_COORDINATES") from None


def rectangle(value: Any) -> list[float]:
    """Reject reversed and empty envelopes."""
    box = numbers(value, 4)
    if box[0] >= box[2] or box[1] >= box[3]:
        raise ValueError("INVALID_RECTANGLE")
    return box


def corners(box: list[float]) -> list[list[float]]:
    """Retain all four corners, before any envelope operation."""
    x0, y0, x1, y1 = box
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


@dataclass(frozen=True)
class TransformChain:
    """Model pixels -> unpadded crop -> visible rotated raster -> top-left pt.

    Crop coordinates are in the already rotated visible raster. Padding is
    left/top/right/bottom in model pixels. No undeclared preprocessing is inferred.
    PDF coordinates are handled separately by the existing PageGeometry class.
    """

    page_size_pt: tuple[float, float]
    raster_size_px: tuple[float, float]
    crop_px: tuple[float, float, float, float]
    input_size_px: tuple[float, float]
    padding_px: tuple[float, float, float, float] = (0, 0, 0, 0)

    def __post_init__(self) -> None:
        for size in (self.page_size_pt, self.raster_size_px, self.input_size_px):
            if min(numbers(size, 2)) <= 0:
                raise ValueError("INVALID_SIZE")
        crop = rectangle(self.crop_px)
        pad = numbers(self.padding_px, 4)
        if not (
            0 <= crop[0] < crop[2] <= self.raster_size_px[0]
            and 0 <= crop[1] < crop[3] <= self.raster_size_px[1]
            and min(pad) >= 0
            and pad[0] + pad[2] < self.input_size_px[0]
            and pad[1] + pad[3] < self.input_size_px[1]
        ):
            raise ValueError("INVALID_TRANSFORM")

    def to_point(self, x: float, y: float) -> list[float]:
        """Map a model pixel; boxes in padding are rejected by the adapter."""
        numbers([x, y], 2)
        left, top, right, bottom = self.padding_px
        cx, cy, cr, cb = self.crop_px
        rx = cx + (x - left) * (cr - cx) / (self.input_size_px[0] - left - right)
        ry = cy + (y - top) * (cb - cy) / (self.input_size_px[1] - top - bottom)
        return [
            rx * self.page_size_pt[0] / self.raster_size_px[0],
            ry * self.page_size_pt[1] / self.raster_size_px[1],
        ]

    def to_input(self, x: float, y: float) -> list[float]:
        """Invert the continuous transform, without integer crop rounding."""
        numbers([x, y], 2)
        left, top, right, bottom = self.padding_px
        cx, cy, cr, cb = self.crop_px
        return [
            left
            + (x * self.raster_size_px[0] / self.page_size_pt[0] - cx)
            * (self.input_size_px[0] - left - right)
            / (cr - cx),
            top
            + (y * self.raster_size_px[1] / self.page_size_pt[1] - cy)
            * (self.input_size_px[1] - top - bottom)
            / (cb - cy),
        ]

    def quad(self, raw: Any, unit: str) -> tuple[list[list[float]], list[list[float]]]:
        """Validate source points and reject detections outside unpadded content."""
        if unit not in {"normalized_1000", "input_pixel"}:
            raise ValueError("UNKNOWN_COORDINATE_UNIT")
        points = (
            corners(rectangle(raw))
            if len(raw) == 4 and not isinstance(raw[0], list)
            else [numbers(p, 2) for p in raw]
        )
        if len(points) != 4:
            raise ValueError("INVALID_QUAD")
        sx, sy = (
            (self.input_size_px[0] / 1000, self.input_size_px[1] / 1000)
            if (unit == "normalized_1000")
            else (1, 1)
        )
        pixels = [[x * sx, y * sy] for x, y in points]
        left, top, right, bottom = self.padding_px
        if any(
            not (
                left <= x <= self.input_size_px[0] - right
                and top <= y <= self.input_size_px[1] - bottom
            )
            for x, y in pixels
        ):
            raise ValueError("GEOMETRY_OUT_OF_INPUT")
        # A genuine ordered quadrilateral must be convex and nondegenerate.
        crosses = []
        for i in range(4):
            a, b, c = points[i], points[(i + 1) % 4], points[(i + 2) % 4]
            crosses.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
        if not (all(v > 0 for v in crosses) or all(v < 0 for v in crosses)):
            raise ValueError("INVALID_QUAD")
        return points, [self.to_point(x, y) for x, y in pixels]

    def record(self) -> Json:
        """Serialize a replayable coordinate contract."""
        return {
            "kind": "crop_resize_pad/1",
            "target": "visible_rotated_top_left_pt",
            **asdict(self),
        }


def full_page(page: Json, info: Json) -> TransformChain:
    """Build the declared no-preprocessing path from stored raster metadata."""
    size = numbers(info["pixel_size"], 2)
    return TransformChain(
        (page["width_pt"], page["height_pt"]),
        (size[0], size[1]),
        (0, 0, size[0], size[1]),
        (size[0], size[1]),
    )


def result() -> Json:
    """Create a provider-local result with no implicit winner."""
    return {"geometry_candidates": [], "selected_geometry_id": None, "rejections": []}


def record(
    provider: str,
    page_index: int,
    index: int,
    label: str,
    level: str,
    granularity: str,
    raw: Any,
    unit: str,
    chain: TransformChain,
    evidence: Json,
    source_slot: str = "regions",
) -> Json:
    """Construct a geometry-only candidate; never copy recognized content."""
    if not isinstance(label, str) or not label or len(label) > 256:
        raise ValueError("INVALID_LABEL")
    raw_quad, quad = chain.quad(raw, unit)
    return {
        "schema_version": "geometry-candidate/1",
        "id": f"p{page_index}-{provider}-{source_slot}-{index}",
        "provider": provider,
        "page_index": page_index,
        "label": label,
        "hierarchy_level": level,
        "granularity": granularity,
        "raw_geometry": raw,
        "raw_quad": raw_quad,
        "raw_unit": unit,
        "quad_pt": quad,
        "bbox_pt": [
            min(p[0] for p in quad),
            min(p[1] for p in quad),
            max(p[0] for p in quad),
            max(p[1] for p in quad),
        ],
        "transform_chain": chain.record(),
        "raw_output_index": index,
        "order_source": "provider_array",
        "order_status": "unknown",
        "provider_order": None,
        "engine_confidence": None,
        "system_confidence": None,
        "evidence": dict(evidence),
    }


def append_unique(output: Json, candidate: Json) -> None:
    """Reject duplicates only within the same provider and granularity."""
    key = (
        candidate["provider"],
        candidate["hierarchy_level"],
        candidate["granularity"],
        candidate["label"],
        candidate["quad_pt"],
    )
    if any(
        (c["provider"], c["hierarchy_level"], c["granularity"], c["label"], c["quad_pt"]) == key
        for c in output["geometry_candidates"]
    ):
        raise ValueError("DUPLICATE_GEOMETRY")
    output["geometry_candidates"].append(candidate)


def attach(page: Json, output: Json) -> None:
    """Attach unselected evidence without changing blocks or reading order."""
    page.setdefault("geometry_candidates", []).extend(output["geometry_candidates"])
    page.setdefault("selected_geometry_id", None)
    page.setdefault("geometry_rejections", []).extend(output["rejections"])
