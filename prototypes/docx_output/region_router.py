"""Offline source regions, editable native runs and whole-figure protection."""

from __future__ import annotations

from pathlib import Path

from .common import Json, block, box_valid, crop, intersection, issue, union
from .formula import unrendered_math
from .native_pdf import cluster_regions
from .page_classifier import abnormal_text, classify_page
from .structure import QUESTION, image_content


def prepare_page(job: Path, ir: Json, p: Json, observation: Json) -> Json:
    """Project observations into disjoint display decisions with retained candidates."""
    index = p["page_index"]
    classification = classify_page(observation)
    p["blocks"] = []
    p["reading_order"] = []
    p["page_type"] = {"hidden_text_scan": "scanned", "broken_encoding": "unknown"}.get(
        classification["page_type"], classification["page_type"]
    )
    p["routing_decision"] = "AUTO_LOCAL_ANALYSIS"
    bounds = [0.0, 0.0, p["width_pt"], p["height_pt"]]
    runs = observation["text_runs"]
    objects = observation["objects"]
    regions: list[Json] = []
    archived: list[Json] = []
    seen: dict[tuple[object, ...], Json] = {}
    for run in runs:
        if not run["text"].strip():
            continue
        bbox = run["bbox"] if box_valid(run["bbox"]) and run["geometry_verified"] else bounds
        bid = f"p{index}-{run['id']}"
        b = block(
            bid,
            index,
            bbox,
            run["text"],
            "native_pdf",
            "question"
            if QUESTION.match(run["text"])
            else "heading"
            if run["font_size"] >= 16
            else "paragraph",
            {
                "native_run_id": run["id"],
                "backend": "pdf-inspector",
                "geometry_precision": run["geometry_precision"],
            },
        )
        b["engine"] = "pdf-inspector"
        b["engine_version"] = observation["backend"]["version"]
        b["content_candidates"][0].update(
            model_id="pdf-inspector", model_version=observation["backend"]["version"]
        )
        b["content"]["runs"] = [
            {
                "text": run["text"],
                "bbox": bbox,
                "font_family": run["font"],
                "font_size_pt": run["font_size"],
                "bold": run["bold"],
                "italic": run["italic"],
                "underline": run["underline"],
                "superscript": run["baseline_shift"] > 0,
                "subscript": run["baseline_shift"] < 0,
                "color": None,
                "confidence": 0,
                "source_ref": bid,
            }
        ]
        ir["provenance"][bid] = {"native_run": run, "backend": "pdf-inspector"}
        key = (run["text"], *(round(v, 2) for v in bbox))
        if key in seen and run["geometry_verified"]:
            old = seen[key]
            b["content_candidates"][0]["selected"] = False
            old["content_candidates"].extend(b["content_candidates"])
            archived.append(
                {"block": b, "reason": "IDENTICAL_TEXT_SAME_GEOMETRY", "selected_block": old["id"]}
            )
            continue
        seen[key] = b
        p["blocks"].append(b)
        if abnormal_text(run["text"]) or not run["geometry_verified"]:
            regions.append({"bbox": bbox, "route": "ocr", "reason": "UNTRUSTED_NATIVE_RUN"})
        elif set(classification["reason_codes"]) & {
            "INVISIBLE_TEXT_WITHOUT_IMAGE",
            "WHITE_PAINT_VISIBILITY_REVIEW",
        }:
            regions.append({"bbox": bbox, "route": "preserve", "reason": "VISIBILITY_REVIEW"})
        elif unrendered_math(run["text"]):
            regions.append({"bbox": bbox, "route": "preserve", "reason": "NATIVE_FORMULA_REVIEW"})
    if classification["content_state"] == "blank":
        return {**classification, "page_index": index, "regions": [], "archived": []}
    images = [o["bbox"] for o in objects if o["type"] == 3 and box_valid(o["bbox"])]
    paths = [o["bbox"] for o in objects if o["type"] == 2 and box_valid(o["bbox"])]
    # A page frame is not a figure and must not swallow every paragraph.
    paths = [
        b
        for b in paths
        if not (
            b[0] <= p["width_pt"] * 0.03
            and b[1] <= p["height_pt"] * 0.03
            and b[2] >= p["width_pt"] * 0.97
            and b[3] >= p["height_pt"] * 0.97
        )
    ]
    for box in cluster_regions(images):
        regions.append({"bbox": box, "route": "inspect", "reason": "IMAGE_PURPOSE_UNKNOWN"})
    for box in cluster_regions(paths):
        if any(intersection(box, image) for image in images):
            continue
        overlap = any(intersection(box, b["bbox"]) for b in p["blocks"])
        regions.append(
            {
                "bbox": box,
                "route": "inspect" if overlap else "preserve",
                "reason": "VECTOR_TEXT_REVIEW" if overlap else "VECTOR_FIGURE",
            }
        )
    if classification["page_type"] == "hidden_text_scan":
        regions = [{"bbox": bounds, "route": "ocr", "reason": "INVISIBLE_TEXT_WITH_IMAGE"}]
    if observation["backend"]["status"] != "OK":
        regions = [{"bbox": bounds, "route": "preserve", "reason": "SOURCE_GEOMETRY_REVIEW"}]
    if not regions and not p["blocks"] and objects:
        regions = [{"bbox": bounds, "route": "preserve", "reason": "UNCLASSIFIED_SOURCE"}]
    # Expand before union so two requests cannot share a native run after expansion.
    for region in regions:
        box = region["bbox"]
        while True:
            native_boxes = [b["bbox"] for b in p["blocks"] if intersection(box, b["bbox"]) > 0]
            expanded = union([box, *native_boxes]) if native_boxes else box
            if expanded == box:
                break
            box = expanded
        region["bbox"] = box
    # Overlapping requests become one source region: never OCR overlapping crops twice.
    merged: list[Json] = []
    for region in regions:
        again = True
        while again:
            again = False
            for other in merged[:]:
                if intersection(region["bbox"], other["bbox"]) > 0:
                    region = {
                        "bbox": union([region["bbox"], other["bbox"]]),
                        "route": "inspect",
                        "reason": "OVERLAPPING_SOURCE_REVIEW",
                    }
                    merged.remove(other)
                    again = True
        merged.append(region)
    for ri, region in enumerate(merged):
        rid = f"p{index}-region{ri}"
        box = region["bbox"]
        box = [max(0.0, box[0]), max(0.0, box[1]), min(bounds[2], box[2]), min(bounds[3], box[3])]
        if not box_valid(box):
            continue
        # Expand to complete intersecting native runs, rather than silently cutting text.
        native = [b for b in p["blocks"] if intersection(box, b["bbox"]) > 0]
        if native:
            box = union([box, *(b["bbox"] for b in native)])
        aid = crop(job, ir, p, box, rid, padding=0)
        pending = block(rid, index, box, "", "pdf_image", "figure")
        pending.update(content=image_content(aid), render_policy="preserve_image")
        for b in native:
            for c in b["content_candidates"]:
                c["selected"] = False
                pending["content_candidates"].append(c)
            p["blocks"].remove(b)
        p["blocks"].append(pending)
        region.update(
            region_id=rid,
            page_index=index,
            bbox=box,
            asset_id=aid,
            source_refs=[o["id"] for o in objects if intersection(box, o["bbox"])],
            native_blocks=native,
            status="PRESERVED" if region["route"] == "preserve" else "AWAITING_AUTHORIZATION",
            transform_id=rid + "-transform",
            request_budget=0 if region["route"] == "preserve" else 2,
        )
        if region["route"] != "preserve" or native:
            issue(
                ir,
                "REGION_ROUTE_REVIEW",
                "区域保留源图及文字候选；识别需要批准区域计划。",
                [rid],
                index,
            )
    p["blocks"].sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
    p["reading_order"] = [b["id"] for b in p["blocks"]]
    return {**classification, "page_index": index, "regions": merged, "archived": archived}
