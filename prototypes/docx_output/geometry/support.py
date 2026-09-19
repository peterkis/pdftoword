"""Independent anchors; recognized PP text may align but never replace content."""

from __future__ import annotations

from collections import Counter

from ..common import Json, area, union
from ..structure_processors.bridge import json_hash
from .candidate import TransformChain, rectangle
from .line_ledger import align, pp_lines


def content_support(page: Json, chain: TransformChain, pp: Json | None = None) -> Json:
    """Require exact unique text evidence; unresolved blocks have no invented sub-box."""
    matches: list[tuple[str, list[float], str]] = []
    if pp is not None:
        try:
            raw = pp["result"]["layoutParsingResults"][0]["prunedResult"]
            if [raw["width"], raw["height"]] != list(chain.input_size_px) or raw.get(
                "model_settings", {}
            ).get("use_doc_preprocessor") is not False:
                raise ValueError("UNVERIFIED_PP_COORDINATES")
            ocr = raw.get("overall_ocr_res", {})
            rows = [
                (text, box, f"line-{i}")
                for i, (text, box) in enumerate(
                    zip(ocr.get("rec_texts", []), ocr.get("rec_boxes", []), strict=True)
                )
            ]
            rows += [
                (r.get("block_content", ""), r["block_bbox"], f"region-{i}")
                for i, r in enumerate(raw.get("parsing_res_list", []))
            ]
            for text, box, ref in rows:
                if not isinstance(text, str) or not text.strip():
                    continue
                try:
                    _, quad = chain.quad(box, "input_pixel")
                    bounds = [
                        min(p[0] for p in quad),
                        min(p[1] for p in quad),
                        max(p[0] for p in quad),
                        max(p[1] for p in quad),
                    ]
                    matches.append(("".join(text.split()), bounds, ref))
                except (ValueError, TypeError):
                    continue
        except (ValueError, KeyError, TypeError, IndexError):
            matches = []
    occurrences = Counter(
        "".join(b["content"].get("plain_text", "").split())
        for b in page["blocks"]
        if b["content"]["kind"] == "text"
    )
    lines = pp_lines(pp, chain) if pp is not None else []
    result = {}
    for block in page["blocks"]:
        content = block["content"]
        basis = None
        refs = []
        bounds = rectangle(block["bbox"])
        if block["geometry_source"] == "native_pdf":
            basis = "native_verified_run"
        elif (
            content["kind"] == "image" and area(bounds) < page["width_pt"] * page["height_pt"] * 0.8
        ):
            basis = "source_figure"
        elif content["kind"] == "text":
            text = "".join(content["plain_text"].split())
            candidates = [(box, ref) for value, box, ref in matches if value == text]
            # A matching line and matching macro box may corroborate a location only
            # when both point to the same area; disjoint identical strings abstain.
            if candidates and occurrences[text] == 1:
                from ..common import intersection

                anchor = candidates[0][0]
                if all(
                    intersection(anchor, box) / min(area(anchor), area(box)) >= 0.98
                    for box, _ in candidates
                ):
                    basis = "exact_pp_text"
                    bounds = union([box for box, _ in candidates])
                    refs = [ref for _, ref in candidates]
        if content["kind"] == "text" and block["geometry_source"] != "native_pdf":
            aligned = (
                align(block, lines)
                if occurrences["".join(content["plain_text"].split())] == 1
                else None
            )
            if aligned:
                result[block["id"]] = aligned
                continue
        if basis:
            result[block["id"]] = {
                "basis": basis,
                "bbox_pt": bounds,
                "source_content_sha256": json_hash(content),
                "support_refs": refs,
            }
    occupied: dict[tuple[str, str], list[tuple[int, int, str]]] = {}
    conflicting: set[str] = set()
    for bid, support in result.items():
        for fragment in support.get("line_fragments", []):
            key = (fragment["response_sha256"], fragment["line_id"])
            start, end = fragment["line_span"]
            for old_start, old_end, owner in occupied.get(key, []):
                if owner != bid and min(end, old_end) > max(start, old_start):
                    conflicting.update((bid, owner))
            occupied.setdefault(key, []).append((start, end, bid))
    return {bid: support for bid, support in result.items() if bid not in conflicting}


def binding_ledger(page: Json, supports: Json) -> Json:
    """Record complete source spans and explicit missing evidence without copying PP prose."""
    from .binding import identity_bindings, inventory

    spans = identity_bindings(page)
    return {
        "schema_version": "geometry-binding-ledger/1",
        "source_inventory": inventory(page),
        "entries": [
            {
                "source_id": b["id"],
                "source_spans": spans[b["id"]],
                "support": supports.get(b["id"]),
                "status": "BOUND" if b["id"] in supports else "UNPROVEN",
                "reason": None if b["id"] in supports else "NO_UNIQUE_SOURCE_LINE_OR_REGION",
            }
            for b in page["blocks"]
        ],
    }
