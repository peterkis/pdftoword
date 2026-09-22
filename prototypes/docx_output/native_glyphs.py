"""Native glyph geometry witnesses; inspector strings remain the content authority."""

from __future__ import annotations

import ctypes
import unicodedata
from collections import Counter
from typing import Any

import pypdfium2 as pdfium  # type: ignore[import-untyped]

from .common import Json, box_valid, intersection, union


def read_glyphs(native: Any, geometry: Any, object_refs: dict[int, Json]) -> list[Json]:
    """Detach PDFium tight boxes and paint ownership while the caller holds its lock."""
    textpage = native.get_textpage()
    result = []
    try:
        for index in range(textpage.count_chars()):
            code = pdfium.raw.FPDFText_GetUnicode(textpage, index)
            text = chr(code) if 0 < code <= 0x10FFFF and not 0xD800 <= code <= 0xDFFF else "\ufffd"
            generated = pdfium.raw.FPDFText_IsGenerated(textpage, index)
            owner = pdfium.raw.FPDFText_GetTextObject(textpage, index)
            obj = object_refs.get(ctypes.cast(owner, ctypes.c_void_p).value or 0, {})
            bbox = None
            try:
                quad = geometry.quad(list(textpage.get_charbox(index)))
                candidate = [
                    min(p[0] for p in quad),
                    min(p[1] for p in quad),
                    max(p[0] for p in quad),
                    max(p[1] for p in quad),
                ]
                if box_valid(candidate):
                    bbox = candidate
            except pdfium.PdfiumError:
                pass
            result.append(
                {
                    "index": index,
                    "text": text,
                    "bbox": bbox,
                    "generated": generated == 1,
                    "generated_known": generated >= 0,
                    "object_id": obj.get("id"),
                    "paint_order": obj.get("paint_order"),
                    "visibility": obj.get("visibility", "unknown"),
                }
            )
    finally:
        textpage.close()
    return result


def bind_runs(runs: list[Json], glyphs: list[Json]) -> Json:
    """Require exact nonspace sequence, unique spatial match and exclusive glyph use."""
    visible = [g for g in glyphs if not g["generated"] and not g["text"].isspace()]
    text = "".join(g["text"] for g in visible)
    result: Json = {}
    for run in runs:
        target = "".join(c for c in run["text"] if not c.isspace())
        record: Json = {
            "status": "NO_GLYPH_MATCH",
            "source_whitespace_offsets": [i for i, c in enumerate(run["text"]) if c.isspace()],
        }
        matches = []
        pos = text.find(target) if target else -1
        while pos >= 0:
            segment = visible[pos : pos + len(target)]
            if all(
                g["bbox"] is not None and intersection(g["bbox"], run["bbox"]) > 0 for g in segment
            ):
                matches.append(segment)
            pos = text.find(target, pos + 1)
        if len(matches) > 1:
            record["status"] = "AMBIGUOUS_GLYPHS"
        elif len(matches) == 1:
            segment = matches[0]
            if any(
                g["visibility"] != "painted"
                or not g.get("generated_known", True)
                or g["text"] == "\ufffd"
                or unicodedata.category(g["text"]) in {"Co", "Cc", "Cs"}
                for g in segment
            ):
                record["status"] = "UNVERIFIED_GLYPHS"
            else:
                indices = [g["index"] for g in segment]
                record.update(
                    status="VERIFIED",
                    char_indices=indices,
                    bbox=union([g["bbox"] for g in segment]),
                    object_ids=sorted({g["object_id"] for g in segment}),
                    paint_orders=sorted({g["paint_order"] for g in segment}),
                    ignored_char_indices=[
                        g["index"]
                        for g in glyphs
                        if indices[0] <= g["index"] <= indices[-1]
                        and (g["generated"] or g["text"].isspace())
                    ],
                )
        result[run["id"]] = record
    uses = Counter(
        i for r in result.values() if r["status"] == "VERIFIED" for i in r["char_indices"]
    )
    for record in result.values():
        if record["status"] == "VERIFIED" and any(uses[i] != 1 for i in record["char_indices"]):
            record["status"] = "GLYPH_REUSED"
    return result
