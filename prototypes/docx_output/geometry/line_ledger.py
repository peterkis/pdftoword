"""Exact content-to-line spans, with no character-count geometry interpolation."""

from __future__ import annotations

from ..common import Json, union
from ..structure_processors.bridge import json_hash
from .candidate import TransformChain


def compact(text: str) -> tuple[str, list[int]]:
    """Keep offsets into original code points while ignoring whitespace for matching only."""
    offsets = [i for i, char in enumerate(text) if not char.isspace()]
    return "".join(text[i] for i in offsets), offsets


def pp_lines(body: Json, chain: TransformChain) -> list[Json]:
    """Detach measured lines with response identity; reject unresolved frame or arrays."""
    try:
        raw = body["result"]["layoutParsingResults"][0]["prunedResult"]
        if [raw["width"], raw["height"]] != list(chain.input_size_px) or raw.get(
            "model_settings", {}
        ).get("use_doc_preprocessor") is not False:
            return []
        ocr = raw.get("overall_ocr_res", {})
        result = []
        for index, (text, box) in enumerate(
            zip(ocr.get("rec_texts", []), ocr.get("rec_boxes", []), strict=True)
        ):
            if not isinstance(text, str) or not text.strip():
                continue
            _, quad = chain.quad(box, "input_pixel")
            result.append(
                {
                    "line_id": f"pp-line-{index}",
                    "raw_index": index,
                    "text": text,
                    "bbox_pt": [
                        min(p[0] for p in quad),
                        min(p[1] for p in quad),
                        max(p[0] for p in quad),
                        max(p[1] for p in quad),
                    ],
                    "response_sha256": json_hash(body),
                    "response_hash_basis": "canonical_json",
                    "line_sha256": json_hash([text, box]),
                }
            )
        return result
    except (ValueError, KeyError, TypeError, IndexError):
        return []


def align(block: Json, lines: list[Json]) -> Json | None:
    """Find one exact contiguous sequence or one bounded fragment; preserve all source chars."""
    text = block["content"]["plain_text"]
    target, offsets = compact(text)
    if not target:
        return None
    sequences: list[list[tuple[Json, int, int]]] = []
    for start in range(len(lines)):
        combined = ""
        parts = []
        for line in lines[start : start + 32]:
            value, _ = compact(line["text"])
            combined += value
            parts.append((line, 0, len(value)))
            if combined == target:
                sequences.append(list(parts))
                break
            if not target.startswith(combined):
                break
    # Only attempt a partial line if complete-line support is absent. A partial
    # line uses the full measured envelope, explicitly not a precise sub-box.
    if not sequences:
        for line in lines:
            value, mapping = compact(line["text"])
            start = value.find(target)
            if start < 0 or value.find(target, start + 1) >= 0:
                continue
            end = start + len(target)
            left, right = mapping[start], mapping[end - 1] + 1
            if (left and not line["text"][left - 1].isspace()) or (
                right < len(line["text"]) and not line["text"][right].isspace()
            ):
                continue
            sequences.append([(line, start, end)])
    if len(sequences) != 1:
        return None
    cursor = 0
    fragments = []
    source_start = 0
    for index, (line, start, end) in enumerate(sequences[0]):
        _, mapping = compact(line["text"])
        count = end - start
        source_end = len(text) if index == len(sequences[0]) - 1 else offsets[cursor + count]
        fragments.append(
            {
                "source_id": block["id"],
                "source_span": [source_start, source_end],
                "source_span_sha256": json_hash(text[source_start:source_end]),
                "line_id": line["line_id"],
                "line_span": [mapping[start], mapping[end - 1] + 1],
                "line_sha256": line["line_sha256"],
                "response_sha256": line["response_sha256"],
                "response_hash_basis": "canonical_json",
                "bbox_pt": line["bbox_pt"],
                "bbox_semantics": "whole_line_envelope",
                "shared_line": start != 0 or end != len(mapping),
            }
        )
        cursor += count
        source_start = source_end
    return {
        "basis": "exact_pp_line_spans",
        "bbox_pt": union([f["bbox_pt"] for f in fragments]),
        "source_content_sha256": json_hash(block["content"]),
        "support_refs": [f["line_id"] for f in fragments],
        "line_fragments": fragments,
        "source_span_ids": [
            json_hash([block["id"], f["source_span"], f["source_span_sha256"]]) for f in fragments
        ],
        "geometry_interpolation": False,
    }
