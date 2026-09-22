"""Bounded proof that a white text backing contributes no source pixels.

Only disposable PDFium copies are altered. The original page remains the asset
source, and rejected proofs do not change rendering ownership.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .common import Json, intersection
from .input_analysis import PDFIUM_LOCK, object_evidence, open_pdf


def neutral_backgrounds(
    source: Path, index: int, objects: list[Json], glyph_evidence: Json | None, regions: list[Json]
) -> Json:
    """Check paint ownership and exact 2x/4x full-page pixels before omitting backing crops."""
    result: Json = {"status": "NO_SAFE_BACKGROUND", "path_ids": [], "native_run_ids": []}
    if glyph_evidence is None:
        return result
    bindings = glyph_evidence["runs"]
    verified = {
        i for r in bindings.values() if r["status"] == "VERIFIED" for i in r["char_indices"]
    }
    glyphs = [g for g in glyph_evidence["glyphs"] if not g["generated"] and not g["text"].isspace()]
    candidates = []
    covered: set[int] = set()
    for obj in objects:
        if (
            obj.get("fill_rgba") != [255, 255, 255, 255]
            or "fill_rect" not in obj
            or obj.get("level") != 0
            or any(intersection(obj["bbox"], r["bbox"]) > 0 for r in regions)
        ):
            continue
        rect = obj["fill_rect"]
        ink = [g for g in glyphs if g["bbox"] is None or intersection(g["bbox"], rect) > 0]
        if not ink or any(
            g["bbox"] is None
            or g["visibility"] != "painted"
            or g["index"] not in verified
            or g["paint_order"] <= obj["paint_order"]
            for g in ink
        ):
            continue
        if any(
            o["type"] != 1
            and o["id"] != obj["id"]
            and intersection(o["bbox"], rect) > 0
            and not ("fill_rect" in o and o.get("fill_rgba") == [255, 255, 255, 255])
            for o in objects
        ):
            continue
        candidates.append(obj)
        covered.update(g["index"] for g in ink)
    if not candidates:
        return result
    ids = {o["id"] for o in candidates}
    result["candidate_path_ids"] = sorted(ids)
    with PDFIUM_LOCK:
        document = open_pdf(source)
        page = None
        removed = []
        try:
            page = document[index]
            if max(page.get_size()) * 4 > 4000:
                result["status"] = "BACKGROUND_PROOF_RENDER_BOUND"
                return result
            before = {}
            for scale in (2, 4):
                bitmap = page.render(scale=scale)
                try:
                    before[scale] = hashlib.sha256(bytes(bitmap.buffer)).hexdigest()
                finally:
                    bitmap.close()
            for oi, (obj, _, _) in enumerate(list(object_evidence(page))):
                if f"p{index}-obj{oi}" in ids:
                    page.remove_obj(obj)
                    removed.append(obj)
            if len(removed) != len(ids):
                result["status"] = "BACKGROUND_OBJECT_MISMATCH"
                return result
            page.gen_content()
            receipts = []
            for scale in (2, 4):
                bitmap = page.render(scale=scale)
                try:
                    after = hashlib.sha256(bytes(bitmap.buffer)).hexdigest()
                finally:
                    bitmap.close()
                receipts.append(
                    {
                        "scale": scale,
                        "before_sha256": before[scale],
                        "after_sha256": after,
                        "identical": before[scale] == after,
                    }
                )
            result["renders"] = receipts
            if not all(r["identical"] for r in receipts):
                result["status"] = "BACKGROUND_HAS_VISIBLE_EFFECT"
                return result
            result.update(
                status="VERIFIED_NO_PIXEL_CONTRIBUTION",
                path_ids=sorted(ids),
                native_run_ids=[
                    rid
                    for rid, r in bindings.items()
                    if r["status"] == "VERIFIED" and set(r["char_indices"]) & covered
                ],
            )
        except (RuntimeError, OSError, ValueError) as exc:
            result.update(
                status="BACKGROUND_PROOF_UNAVAILABLE",
                path_ids=[],
                native_run_ids=[],
                error_type=type(exc).__name__,
            )
        finally:
            # Removed handles become caller-owned and must close before their page.
            for obj in removed:
                obj.close()
            if page is not None:
                page.close()
            document.close()
    return result
