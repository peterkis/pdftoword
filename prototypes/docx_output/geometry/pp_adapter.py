"""PP semantic regions and line/formula support, excluding recognized content."""

from __future__ import annotations

from ..common import Json
from .candidate import MAX_REGIONS, TransformChain, append_unique, numbers, record, result


def adapt(body: Json, page_index: int, chain: TransformChain, evidence: Json) -> Json:
    """Honor only the known pixel contract; PP array order is not learned order."""
    output = result()
    try:
        if body.get("errorCode", 0) != 0:
            raise ValueError("PROVIDER_ERROR")
        pages = body["result"]["layoutParsingResults"]
        if not isinstance(pages, list) or len(pages) != 1:
            raise ValueError("INVALID_PAGE_COUNT")
        page = pages[0]["prunedResult"]
        if numbers([page["width"], page["height"]], 2) != list(chain.input_size_px):
            raise ValueError("COORDINATE_MAPPING_UNRESOLVED")
        if page.get("model_settings", {}).get("use_doc_preprocessor") is not False:
            raise ValueError("PREPROCESSING_UNVERIFIED")
        groups = [
            ("regions", page.get("parsing_res_list", [])),
            ("lines", page.get("overall_ocr_res", {}).get("rec_boxes", [])),
            ("formulas", page.get("formula_res_list", [])),
        ]
        if any(not isinstance(rows, list) for _, rows in groups):
            raise ValueError("INVALID_REGION_ARRAY")
        if sum(len(rows) for _, rows in groups) > MAX_REGIONS:
            raise ValueError("REGION_COUNT_LIMIT")
    except (ValueError, KeyError, TypeError, AttributeError, IndexError):
        output["rejections"].append(
            {"provider": "pp", "index": None, "reason": "PP_CONTRACT_REJECTED"}
        )
        return output
    for slot, rows in groups:
        for index, row in enumerate(rows):
            try:
                if slot == "regions":
                    label, raw, level, granularity = (
                        row["block_label"],
                        row["block_bbox"],
                        "region",
                        "semantic_region",
                    )
                elif slot == "lines":
                    label, raw, level, granularity = "text", row, "line", "ocr_line_box"
                else:
                    label, raw, level, granularity = (
                        "formula",
                        row["dt_polys"],
                        "region",
                        "formula_box",
                    )
                candidate = record(
                    "pp",
                    page_index,
                    index,
                    label,
                    level,
                    granularity,
                    raw,
                    "input_pixel",
                    chain,
                    evidence,
                    slot,
                )
                if slot == "regions":
                    # Preserve actual provider fields; never synthesize absent model keys.
                    candidate["provider_order"] = {
                        key: row[key]
                        for key in ("block_id", "block_order")
                        if isinstance(row.get(key), int) and not isinstance(row[key], bool)
                    } or None
                    if candidate["provider_order"] is not None:
                        candidate["order_source"] = "provider_fields"
                        candidate["order_status"] = "partial"
                append_unique(output, candidate)
            except (ValueError, TypeError, KeyError, IndexError):
                output["rejections"].append(
                    {
                        "provider": "pp",
                        "index": index,
                        "slot": slot,
                        "reason": "INVALID_OR_DUPLICATE_GEOMETRY",
                    }
                )
    return output
