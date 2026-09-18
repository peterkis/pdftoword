"""Native measured run evidence, preserving the existing PDF coordinate basis."""

from __future__ import annotations

from ..common import Json
from ..input_analysis import PageGeometry, envelope
from .candidate import MAX_REGIONS, corners, numbers, rectangle, result


def adapt(observation: Json, page_index: int, evidence: Json) -> Json:
    """Preserve verified advance/em run envelopes without claiming tight glyph ink."""
    output = result()
    try:
        data = observation["geometry"]
        box = rectangle(data["visible_box"])
        rotation = data["rotation"]
        if isinstance(rotation, bool) or rotation not in (0, 90, 180, 270):
            raise ValueError("UNKNOWN_ROTATION")
        geometry = PageGeometry((box[0], box[1], box[2], box[3]), rotation)
        rows = observation["text_runs"]
        if not isinstance(rows, list) or len(rows) > MAX_REGIONS:
            raise ValueError("REGION_COUNT_LIMIT")
    except (ValueError, KeyError, TypeError):
        output["rejections"].append(
            {"provider": "native", "index": None, "reason": "NATIVE_CONTRACT_REJECTED"}
        )
        return output
    for index, row in enumerate(rows):
        try:
            if row.get("geometry_verified") is not True:
                raise ValueError("UNVERIFIED_NATIVE_GEOMETRY")
            raw = rectangle(row["raw_bbox_pdf"])
            quad = geometry.quad(raw)
            stored = [numbers(p, 2) for p in row["quad_pt"]]
            if len(stored) != 4 or any(
                abs(a - b) > 1e-7
                for p, q in zip(quad, stored, strict=True)
                for a, b in zip(p, q, strict=True)
            ):
                raise ValueError("INCONSISTENT_NATIVE_TRANSFORM")
            bounds = envelope(quad)
            # The observer allows at most 1 pt beyond the effective canvas; preserve,
            # do not clamp the measured envelope into a fabricated tight glyph box.
            if not (
                0 <= bounds[0] < bounds[2] <= geometry.width + 1
                and 0 <= bounds[1] < bounds[3] <= geometry.height + 1
            ):
                raise ValueError("NATIVE_OUT_OF_PAGE")
            output["geometry_candidates"].append(
                {
                    "schema_version": "geometry-candidate/1",
                    "id": f"p{page_index}-native-runs-{index}",
                    "provider": "native",
                    "page_index": page_index,
                    "label": "text",
                    "hierarchy_level": "line",
                    "granularity": "native_advance_em_run",
                    "raw_geometry": raw,
                    "raw_quad": corners(raw),
                    "raw_unit": "pdf_point",
                    "quad_pt": quad,
                    "bbox_pt": bounds,
                    "transform_chain": {
                        "kind": "pdf_visible/1",
                        "target": "visible_rotated_top_left_pt",
                        **geometry.record(),
                    },
                    "raw_output_index": index,
                    "order_source": "native_stream",
                    "order_status": "unknown",
                    "provider_order": None,
                    "engine_confidence": None,
                    "system_confidence": None,
                    "evidence": {**evidence, "source_run_id": row["id"], "geometry_verified": True},
                }
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            output["rejections"].append(
                {"provider": "native", "index": index, "reason": "INVALID_OR_UNVERIFIED_NATIVE_RUN"}
            )
    return output
