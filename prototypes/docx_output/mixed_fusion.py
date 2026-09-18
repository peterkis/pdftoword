"""Region reconstruction isolated from whole-page state and mapped back once."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

from .common import DemoError, Json, candidate, digest, issue, layout, new_job, page, safe_path


def reconstruct_region(job: Path, ir: Json, region: Json, responses: Json, manifest: Json) -> None:
    """Build in a private region sandbox; merge only after valid isolated reconstruction."""
    from .pipeline import reconstruct

    index = region["page_index"]
    target = next(p for p in ir["pages"] if p["page_index"] == index)
    source = safe_path(job, next(a["path"] for a in ir["assets"] if a["id"] == region["asset_id"]))
    # Reconstruct uses integer crop pixels as local page units; invert using actual crop origin.
    info = ir["provenance"]["pages"][str(index)]
    crop_pixels = ir["provenance"][region["asset_id"]]["crop_bbox_px"]
    sx, sy = info["pixel_to_point"]
    ox, oy = crop_pixels[0] * sx, crop_pixels[1] * sy
    work = new_job(job / "regions")
    shutil.copyfile(source, work / "assets/source-0.png")
    local = layout(work, source, 1)
    w, h = region["pixel_size"]
    p = page(0, w, h, "scanned")
    local["pages"].append(p)
    local["provenance"]["pages"] = {
        "0": {
            "image_path": "assets/source-0.png",
            "image_sha256": digest(work / "assets/source-0.png"),
            "pixel_size": [w, h],
            "pixel_to_point": [1, 1],
            "point_to_pixel": [1, 1],
            "size_basis": "region_pixels",
        }
    }
    calls = {
        "requests": [
            {**r, "page_index": 0}
            for r in manifest["requests"]
            if r["region_id"] == region["region_id"]
        ]
    }
    from .region_content import normalize_region_content

    normalized, fallbacks = normalize_region_content(responses, [w, h])
    reconstruct(work, local, p, normalized, calls, "ovis-pp")
    for fallback in fallbacks:
        for b in p["blocks"]:
            if local["provenance"].get(b["id"], {}).get("raw_image_tag") == fallback["tag"]:
                b["flags"].append("REGION_TABLE_FALLBACK")
                b["type"] = "table"
                b["geometry_source"] = "pp_structure"
                local["provenance"][b["id"]]["geometry_derivation"] = {
                    "provider": "pp_structure",
                    "bbox_px": fallback["bbox_px"],
                    "normalization": "outward-rounded normalized_1000 image reference",
                }

                b["content_candidates"].append(
                    candidate(
                        b["id"] + "-table-candidate",
                        "ovis_ocr2",
                        fallback["raw_markup"],
                        {"reason": fallback["reason"], "source_span": fallback["source_span"]},
                        selected=False,
                    )
                )
                issue(
                    local,
                    "REGION_TABLE_FALLBACK",
                    "表格保留局部源图，周围正文保持可编辑。",
                    [b["id"]],
                    0,
                )
    local["provenance"]["region_content_fallbacks"] = fallbacks
    if not any(
        b["content"]["kind"] == "text" and b["content"].get("plain_text", "").strip()
        for b in p["blocks"]
    ):
        raise DemoError("REGION_NO_EDITABLE_CONTENT")
    # Conflicting native content cannot be discarded just because OCR returned more words.
    native = region["native_blocks"]
    if native and region["reason"] not in ("INVISIBLE_TEXT_WITH_IMAGE", "UNTRUSTED_NATIVE_RUN"):
        raise DemoError("NATIVE_REGION_CONFLICT")
    prefix = region["region_id"] + "-"
    ids = {b["id"] for b in p["blocks"]} | {a["id"] for a in local["assets"]}
    ids |= {c["id"] for b in p["blocks"] for c in b["content_candidates"]}
    ids |= set(local["provenance"]) | {r["id"] for r in local["relations"]}
    ids |= {i["id"] for i in local["issues"]}
    mapping = {key: prefix + key for key in ids if key != "pages"}

    def remap(value: Any) -> Any:
        if isinstance(value, str):
            return mapping.get(value, value)
        if isinstance(value, list):
            return [remap(v) for v in value]
        if isinstance(value, dict):
            return {mapping.get(k, k): remap(v) for k, v in value.items()}
        return value

    def mapped_box(box: list[float]) -> list[float]:
        return [ox + box[0] * sx, oy + box[1] * sy, ox + box[2] * sx, oy + box[3] * sy]

    additions = []
    for original in p["blocks"]:
        b = remap(copy.deepcopy(original))
        b["page_index"] = index
        b["bbox"] = mapped_box(b["bbox"])
        for run in b["content"].get("runs", []):
            if run.get("bbox"):
                run["bbox"] = mapped_box(run["bbox"])
        for c in b["content_candidates"]:
            c["evidence"]["region_id"] = region["region_id"]
            if native:
                c["evidence"]["supersedes"] = [n["selected_candidate_id"] for n in native]
                c["evidence"]["replacement_reason"] = region["reason"]
        additions.append(b)
    if native and additions:
        for original in native:
            for previous in original["content_candidates"]:
                preserved = copy.deepcopy(previous)
                preserved["selected"] = False
                additions[0]["content_candidates"].append(preserved)
    for original in local["assets"]:
        a = remap(copy.deepcopy(original))
        rel = str((work / original["path"]).relative_to(job))
        a.update(path=rel, source_page_index=index, source_bbox=mapped_box(a["source_bbox"]))
        ir["assets"].append(a)
    for key, value in local["provenance"].items():
        if key != "pages":
            ir["provenance"][mapping[key]] = remap(value)
    ir["provenance"][prefix + "transform"] = {
        "region_id": region["region_id"],
        "crop_bbox_px": crop_pixels,
        "pixel_to_point": [sx, sy],
        "origin_pt": [ox, oy],
        "native_candidates": native,
    }
    for key in ("inline_parts", "option_groups"):
        if isinstance(local["metadata"].get(key), dict):
            ir["metadata"].setdefault(key, {}).update(remap(local["metadata"][key]))
    for group in remap(local["metadata"].get("text_groups", [])):
        group["page_index"] = index
        if group.get("bbox"):
            group["bbox"] = mapped_box(group["bbox"])
        ir["metadata"].setdefault("text_groups", []).append(group)
    ir["relations"].extend(remap(local["relations"]))
    for item in remap(local["issues"]):
        item["page_index"] = index
        ir["issues"].append(item)
    position = next(i for i, b in enumerate(target["blocks"]) if b["id"] == region["region_id"])
    target["blocks"][position : position + 1] = additions
    target["reading_order"] = [b["id"] for b in target["blocks"]]
    for item in ir["issues"]:
        if item["type"] == "REGION_ROUTE_REVIEW" and region["region_id"] in item["block_ids"]:
            item["block_ids"] = [b["id"] for b in additions]
            item["status"] = "resolved"
