"""Offline, evidence-based refinement of pdf-inspector classification."""

from __future__ import annotations

import unicodedata

from .common import Json, union_area


def abnormal_text(text: str) -> bool:
    """Detect unreliable mappings without correcting the original characters."""
    return any(
        c == "\ufffd"
        or unicodedata.category(c) in ("Co", "Cs")
        or (not c.isprintable() and c not in "\r\n\t")
        for c in text
    )


def classify_page(observation: Json) -> Json:
    """Refine coarse backend labels using observed objects, never requesting OCR."""
    runs = observation["text_runs"]
    objects = observation["objects"]
    geometry = observation["geometry"]
    page_area = geometry["width_pt"] * geometry["height_pt"]
    images = [o["bbox"] for o in objects if o["type"] == 3]
    coverage = min(1.0, union_area(images) / page_area)
    text_objects = [o for o in objects if o["type"] == 1]
    reasons = []
    kind = "native"
    state = "native"
    if observation["backend"]["status"] != "OK":
        kind = "unknown"
        reasons.append("NATIVE_EXTRACTION_FAILED")
    elif not objects and not runs:
        state = "blank"
    elif not runs:
        kind = "scanned" if images else "unknown"
        state = "image_only"
        reasons.append("NO_NATIVE_TEXT")
    elif any(abnormal_text(r["text"]) for r in runs):
        kind = "broken_encoding"
        reasons.append("ABNORMAL_UNICODE")
    elif images and text_objects and all(o["visibility"] == "invisible" for o in text_objects):
        kind = "hidden_text_scan"
        reasons.append("INVISIBLE_TEXT_WITH_IMAGE")
    elif text_objects and all(o["visibility"] == "invisible" for o in text_objects):
        kind = "unknown"
        reasons.append("INVISIBLE_TEXT_WITHOUT_IMAGE")
    elif text_objects and any(o["visibility"] == "white_paint" for o in text_objects):
        kind = "unknown"
        reasons.append("WHITE_PAINT_VISIBILITY_REVIEW")
    elif any(not r["geometry_verified"] for r in runs):
        kind = "unknown"
        reasons.append("UNVERIFIED_NATIVE_GEOMETRY")
    elif images:
        kind = "mixed"
        reasons.append("IMAGE_PURPOSE_UNCONFIRMED")
    if any(o.get("level", 0) for o in objects):
        reasons.append("NESTED_FORM_GEOMETRY_REVIEW")
    if len(runs) != len({(r["text"], tuple(round(v, 2) for v in r["bbox"])) for r in runs}):
        reasons.append("DUPLICATE_NATIVE_RUNS")
    return {
        "schema_version": "page-classification/1",
        "page_type": kind,
        "content_state": state,
        "reason_codes": reasons,
        "evidence_refs": [r["id"] for r in runs] + [o["id"] for o in objects],
        "image_coverage": coverage,
        "confidence": None,
        "backend_classification": observation["backend"].get("classification", {}),
        "uncertainty": reasons,
    }
