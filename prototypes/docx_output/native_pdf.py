"""Finite PDFium native extraction and rendering, serialized by a single mutex."""

from __future__ import annotations

import itertools
import math
import unicodedata
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-untyped]

from .common import (
    DemoError,
    Json,
    area,
    block,
    box_valid,
    crop,
    digest,
    intersection,
    invalid_xml_text,
    issue,
    page,
    union,
    union_area,
)
from .formula import unrendered_math
from .geometry.candidate import attach
from .geometry.native_adapter import adapt as native_geometry
from .input_analysis import PDFIUM_LOCK, PdfInspectorBackend, observe_page, open_pdf
from .structure import QUESTION, image_content


def _abnormal_unicode(char: str) -> bool:
    """Identify unreliable glyph mappings, including supplementary private-use planes."""
    return (
        (not char.isprintable() and char not in "\t\r\n")
        or char == "\ufffd"
        or unicodedata.category(char) == "Co"
    )


def parse_pages(selection: str | None, total: int) -> list[int]:
    """Parse 1-based page selections, reject excess instead of silently truncating."""
    selected = []
    for part in (selection or f"1-{total}").split(","):
        try:
            ends = [int(n) for n in part.split("-")]
        except ValueError as exc:
            raise DemoError("INVALID_PAGE_SELECTION") from exc
        if len(ends) == 1:
            selected.append(ends[0] - 1)
        elif len(ends) == 2 and 1 <= ends[0] <= ends[1] <= total:
            if ends[1] - ends[0] >= 3:
                raise DemoError("MAX_THREE_PAGES")
            selected.extend(range(ends[0] - 1, ends[1]))
        else:
            raise DemoError("INVALID_PAGE_SELECTION")
    if not 1 <= len(selected) <= 3 or len(set(selected)) != len(selected):
        raise DemoError("MAX_THREE_DISTINCT_PAGES")
    if any(i < 0 or i >= total for i in selected):
        raise DemoError("PAGE_OUT_OF_RANGE")
    return selected


def cluster_regions(boxes: list[list[float]], gap: float = 10) -> list[list[float]]:
    """Group adjacent vector paths/image components into complete figure regions."""
    result: list[list[float]] = []
    for box in boxes:
        merged = box
        again = True
        while again:
            again = False
            for other in result[:]:
                grown = [merged[0] - gap, merged[1] - gap, merged[2] + gap, merged[3] + gap]
                if intersection(grown, other) > 0:
                    merged = union([merged, other])
                    result.remove(other)
                    again = True
        result.append(merged)
    return result


def extract(
    job: Path, ir: Json, source: Path, selection: str | None, raster_only: bool = False
) -> None:
    """Extract native text/font/bbox and local figure crops, never performing OCR."""
    extracted = PdfInspectorBackend().extract(source) if not raster_only else {}
    with PDFIUM_LOCK:
        document = open_pdf(source)
        try:
            if pdfium.raw.FPDF_GetSecurityHandlerRevision(document) >= 0:
                raise DemoError("PDF_PASSWORD_REQUIRED_UNSUPPORTED")
            if not len(document):
                raise DemoError("PDF_EMPTY_DOCUMENT")
            selected = parse_pages(selection, len(document))
            ir["source"]["page_count"] = len(document)
            ir["metadata"]["selected_pages_1based"] = [i + 1 for i in selected]
            for index in selected:
                native = document[index]
                bitmap = None
                try:
                    w, h = native.get_size()
                    if not math.isfinite(w + h) or min(w, h) <= 0:
                        raise DemoError("INVALID_PAGE_SIZE")
                    scale = min(2.0, 4000 / max(w, h))
                    try:
                        bitmap = native.render(scale=scale)
                    except pdfium.PdfiumError as exc:
                        raise DemoError("PDF_RENDER_FAILED") from exc
                    converter = bitmap.get_posconv(native)
                    bw, bh = bitmap.width, bitmap.height
                    p = page(index, w, h, "native")
                    ir["pages"].append(p)
                    path = job / "assets" / f"source-{index}.png"
                    image = bitmap.to_pil()
                    try:
                        image.save(path)
                    finally:
                        image.close()
                    path.chmod(0o600)
                    info = {
                        "image_path": str(path.relative_to(job)),
                        "image_sha256": digest(path),
                        "pixel_size": [bw, bh],
                        "pixel_to_point": [w / bw, h / bh],
                        "point_to_pixel": [bw / w, bh / h],
                        "size_basis": "PDFium_effective_cropbox_and_rotation",
                        "cropbox_pdf": list(native.get_bbox()),
                        "rotation_pdf": native.get_rotation(),
                        "source_page_1based": index + 1,
                        "pdf_to_bitmap_basis": [
                            converter.to_bitmap(0, 0),
                            converter.to_bitmap(1, 0),
                            converter.to_bitmap(0, 1),
                        ],
                    }
                    ir["provenance"].setdefault("pages", {})[str(index)] = info
                    if raster_only:
                        p["page_type"] = "scanned"
                        continue

                    observation = observe_page(native, index, extracted)
                    g = observation.geometry
                    from .common import save

                    save(job / f"observation-{index}.json", observation.record())
                    info["native_backend"] = observation.backend
                    info["page_geometry"] = g.record()
                    attach(p, native_geometry(observation.record(), index, {
                        "observation_sha256": digest(job / f"observation-{index}.json"),
                        "backend": observation.backend.get("backend"),
                        "backend_version": observation.backend.get("version"),
                    }))
                    path_boxes = []
                    image_boxes = []
                    for obj in observation.objects:
                        bounds = list(obj["bbox"])
                        if bounds[2] == bounds[0]:
                            bounds[2] += 1
                        if bounds[3] == bounds[1]:
                            bounds[3] += 1
                        if box_valid(bounds):
                            if obj["type"] == pdfium.raw.FPDF_PAGEOBJ_IMAGE:
                                image_boxes.append(bounds)
                            elif obj["type"] == pdfium.raw.FPDF_PAGEOBJ_PATH:
                                path_boxes.append(bounds)
                    chars: list[Json] = []
                    source_chars = [r["text"] for r in observation.text_runs]
                    bad = 0
                    invalid_box = 0
                    angles = 0
                    for ri, run in enumerate(observation.text_runs):
                        bad += sum(_abnormal_unicode(c) for c in run["text"])
                        if not run["geometry_verified"]:
                            invalid_box += 1
                            continue
                        angles += bool(run["rotation"])
                        chars.append(
                            {
                                "text": run["text"],
                                "bbox": run["bbox"],
                                "font": run["font"],
                                "size": run["font_size"],
                                "font_size_verified": True,
                                "bold": run["bold"],
                                "italic": run["italic"],
                                "underline": run["underline"],
                                "index": ri,
                                "source_id": run["id"],
                            }
                        )
                    if observation.backend["status"] != "OK":
                        invalid_box += 1
                    full_background = [
                        bounds for bounds in image_boxes if area(bounds) / (w * h) >= 0.9
                    ]
                    info["background_image_bounds"] = full_background
                    if invalid_box or full_background:
                        bounds = [0.0, 0.0, w, h]
                        bid = f"p{index}-native-geometry-fallback"
                        b = block(
                            bid,
                            index,
                            bounds,
                            "".join(source_chars),
                            "native_pdf",
                            evidence={
                                "reason": "unverified_background_text_layer"
                                if full_background
                                else "invalid_character_geometry"
                            },
                        )
                        aid = crop(job, ir, p, bounds, bid)
                        b.update(content=image_content(aid), render_policy="preserve_image")
                        p["blocks"].append(b)
                        p["reading_order"] = [bid]
                        p["routing_decision"] = (
                            "NATIVE_BACKGROUND_FALLBACK"
                            if full_background
                            else "NATIVE_GEOMETRY_FALLBACK"
                        )
                        issue(
                            ir,
                            "NATIVE_BACKGROUND_FALLBACK"
                            if full_background
                            else "NATIVE_GEOMETRY_FALLBACK",
                            "原生坐标或背景文字层完整性不确定，保留完整字符候选并降级源页。",
                            [bid],
                            index,
                        )
                        continue
                    # Path envelopes may be page/table borders, not actual ink coverage.
                    # Never let these ambiguous containers suppress valid native text.
                    ambiguous_paths = [
                        bounds
                        for bounds in path_boxes
                        if any(intersection(c["bbox"], bounds) > 0 for c in chars)
                    ]
                    info["ambiguous_vector_bounds"] = ambiguous_paths
                    backgrounds = [
                        bounds for bounds in image_boxes if area(bounds) / (w * h) >= 0.9 and chars
                    ]
                    info["background_image_bounds"] = backgrounds
                    figures = cluster_regions(
                        [
                            *(b for b in image_boxes if b not in backgrounds),
                            *(b for b in path_boxes if b not in ambiguous_paths),
                        ]
                    )
                    # Include adjacent lettering in the composite crop only.
                    for fi, f in enumerate(figures):
                        grown = [f[0] - 5, f[1] - 5, f[2] + 5, f[3] + 5]
                        internal = [
                            c["bbox"]
                            for c in chars
                            if intersection(c["bbox"], grown) / area(c["bbox"]) > 0.8
                        ]
                        if internal:
                            figures[fi] = union([f, *internal])
                    # Containment does not prove that native text belongs to a figure.
                    visible_chars = chars
                    image_text_overlap = any(
                        intersection(c["bbox"], bounds) > 0 for bounds in image_boxes for c in chars
                    )
                    # Keep ambiguous vector ink as an explicit review crop as well;
                    # it never suppresses the editable native text above.
                    ambiguous_figures = [
                        bounds
                        for bounds in cluster_regions(ambiguous_paths)
                        if not (
                            bounds[0] <= w * 0.03
                            and bounds[1] <= h * 0.03
                            and bounds[2] >= w * 0.97
                            and bounds[3] >= h * 0.97
                        )
                    ]
                    figures.extend(ambiguous_figures)
                    duplicate = len(chars) - len(
                        {(c["text"], tuple(round(v, 1) for v in c["bbox"])) for c in chars}
                    )
                    img_ratio = union_area(image_boxes) / (w * h)
                    reason = ["vector_text_overlap_review"] if ambiguous_paths else []
                    info["font_size_rule"] = "pdf_inspector_effective_run_font_size"
                    if any(not c["font_size_verified"] for c in chars):
                        reason.append("unverified_font_size_using_default_style")
                    if image_text_overlap:
                        reason.append("image_text_overlap_review")
                    count = max(1, sum(len(c["text"]) for c in chars))
                    if bad:
                        reason.append("abnormal_unicode")
                    if invalid_box / count > 0.01:
                        reason.append("invalid_bbox")
                    if duplicate / count > 0.02:
                        reason.append("duplicate_text_layer")
                    if img_ratio > 0.5:
                        reason.append("image_dominant_or_hidden_text")
                    if angles or native.get_rotation():
                        reason.append("rotated_text_review")
                    if not chars:
                        reason.append("scan_candidate")
                    rows: list[list[Json]] = []
                    for c in sorted(visible_chars, key=lambda a: (a["bbox"][1], a["bbox"][0])):
                        center = (c["bbox"][1] + c["bbox"][3]) / 2
                        near = [
                            r
                            for r in rows
                            if abs(center - (r[0]["bbox"][1] + r[0]["bbox"][3]) / 2)
                            < max(2.0, c["size"] * 0.35)
                        ]
                        if near:
                            near[-1].append(c)
                        else:
                            rows.append([c])
                    for ni, row in enumerate(rows):
                        row.sort(key=lambda c: c["bbox"][0])
                        text = "".join(c["text"] for c in row)
                        bbox = union([c["bbox"] for c in row])
                        if any(
                            b["bbox"][0] - a["bbox"][2] > max(40, a["size"] * 4)
                            for a, b in itertools.pairwise(row)
                        ):
                            reason.append("possible_columns_or_table")
                        bid = f"p{index}-native{ni}"
                        b = block(
                            bid,
                            index,
                            bbox,
                            text,
                            "native_pdf",
                            "question" if QUESTION.match(text) else "paragraph",
                            {
                                "native_run_ids": [c["source_id"] for c in row],
                                "backend": "pdf-inspector",
                            },
                        )
                        b["content"]["runs"] = [
                            {
                                "text": c["text"],
                                "bbox": c["bbox"],
                                "font_family": c["font"] or None,
                                "font_size_pt": c["size"] if c["font_size_verified"] else None,
                                "bold": c["bold"],
                                "italic": c["italic"],
                                "underline": c["underline"],
                                "superscript": False,
                                "subscript": False,
                                "color": None,
                                "confidence": 0,
                                "source_ref": bid,
                            }
                            for c in row
                        ]
                        if row[0]["size"] >= 16:
                            b["type"] = "heading"
                        alternate_formula = unrendered_math(text)
                        abnormal_unicode = any(_abnormal_unicode(c) for c in text)
                        invalid_xml = invalid_xml_text(text)
                        if alternate_formula or abnormal_unicode or invalid_xml:
                            aid = crop(job, ir, p, bbox, bid + "-invalid-xml")
                            b.update(content=image_content(aid), render_policy="preserve_image")
                            b["flags"].append("invalid_xml_text_fallback")
                            issue(
                                ir,
                                "NATIVE_FORMULA_DELIMITER_REVIEW"
                                if alternate_formula
                                else "INVALID_XML_TEXT_FALLBACK"
                                if invalid_xml
                                else "NATIVE_UNICODE_FALLBACK",
                                "原生行含未支持公式定界符、异常字形映射或XML非法字符，保留候选并降级源图待审校。",
                                [bid],
                                index,
                            )
                        b["engine"] = "pdf-inspector"
                        b["engine_version"] = extracted["version"]
                        for candidate in b["content_candidates"]:
                            candidate["model_id"] = "pdf-inspector"
                            candidate["model_version"] = extracted["version"]
                        p["blocks"].append(b)
                        ir["provenance"][bid] = {
                            "native_run_ids": [c["source_id"] for c in row],
                            "backend": "pdf-inspector",
                        }
                    for fi, f in enumerate(figures):
                        bid = f"p{index}-figure{fi}"
                        aid = crop(job, ir, p, f, bid)
                        b = block(bid, index, f, "", "pdf_vector_render", "figure")
                        b.update(content=image_content(aid), render_policy="preserve_image")
                        if f in ambiguous_figures:
                            b["flags"].append("ambiguous_vector_reference")
                            issue(
                                ir,
                                "VECTOR_TEXT_OVERLAP_REVIEW",
                                "矢量图域含原生文字，保留参考裁剪与可编辑文字；图内文字可能重复，需复核图域边界。",
                                [bid],
                                index,
                            )
                        p["blocks"].append(b)
                        if area(f) / (w * h) > 0.5:
                            issue(
                                ir,
                                "FIGURE_REGION_REVIEW",
                                "大图域边界需人工框选确认。",
                                [bid],
                                index,
                            )
                    p["blocks"].sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
                    p["reading_order"] = [b["id"] for b in p["blocks"]]
                    p["routing_decision"] = (
                        "NEEDS_ROUTE_REVIEW" if reason else "NATIVE_LIMITED_SUPPORTED"
                    )
                    if not chars:
                        p["page_type"] = "image_dominant"
                    info["classification_evidence"] = {
                        "printable_ratio": 1 - bad / count,
                        "invalid_bbox_ratio": invalid_box / count,
                        "duplicate_ratio": duplicate / count,
                        "page_image_area_ratio": img_ratio,
                        "reasons": sorted(set(reason)),
                        "native_text_before_figure_suppression": "".join(c["text"] for c in chars),
                    }
                    if reason:
                        issue(
                            ir,
                            "NEEDS_ROUTE_REVIEW",
                            "页面超出简单原生入口："
                            + ", ".join(sorted(set(reason)))
                            + "；已保留可恢复文字和图域，不自动OCR。",
                            p["reading_order"],
                            index,
                        )
                finally:
                    try:
                        if bitmap is not None:
                            bitmap.close()
                    finally:
                        native.close()
        finally:
            document.close()
