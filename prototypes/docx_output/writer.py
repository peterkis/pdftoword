"""Real flowing DOCX writer and package-level integrity checks."""

from __future__ import annotations

import io
import posixpath
import unicodedata
import zipfile
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from lxml import etree
from PIL import Image

from .common import DemoError, Json, safe_path, validate
from .formula import unrendered_math


def fonts() -> Json:
    """Detect available local font families without distributing font files."""
    roots = [Path("/System/Library/Fonts"), Path("/Library/Fonts"), Path.home() / "Library/Fonts"]
    names = [p.name.lower() for r in roots if r.exists() for p in r.rglob("*") if p.is_file()]
    east = next(
        (
            family
            for token, family in [
                ("pingfang", "PingFang SC"),
                ("songti", "Songti SC"),
                ("notosanscjk", "Noto Sans CJK SC"),
            ]
            if any(token in n for n in names)
        ),
        None,
    )
    latin = next(
        (
            family
            for token, family in [("arial", "Arial"), ("times", "Times New Roman")]
            if any(token in n for n in names)
        ),
        None,
    )
    return {
        "east_asia": east,
        "latin": latin,
        "missing": not east or not latin,
        "raster_style": "inferred_demo_11pt",
    }


def text_column_widths(
    rows: list[list[str]], blocks: Json, width: float, parts: Json
) -> list[float]:
    """Allocate display widths for plain-text cells; never manufacture source bboxes."""
    count = max(len(row) for row in rows)
    equal = width / count
    if any(bid in parts for row in rows for bid in row):
        return [equal] * count
    minimum = [0.0] * count
    for row in rows:
        for column, bid in enumerate(row):
            text = blocks[bid]["content"].get("plain_text", "")
            units = sum(1.0 if unicodedata.east_asian_width(c) in {"W", "F"} else 0.5 for c in text)
            minimum[column] = max(minimum[column], units * 11 + 12)
    if sum(minimum) >= width:
        return [equal] * count  # Keep natural wrapping; never shrink the text.
    widths = [max(equal, m) for m in minimum]
    excess = sum(widths) - width
    spare = sum(w - m for w, m in zip(widths, minimum, strict=True))
    return [
        w - excess * (w - m) / spare if spare else w for w, m in zip(widths, minimum, strict=True)
    ]


def build(job: Path, ir: Json, revision: str) -> Json:
    """Consume validated IR only; never query a model or overwrite auto output."""
    validate(ir)
    if revision not in {"auto", "reviewed"}:
        raise DemoError("INVALID_REVISION")
    path = safe_path(job, f"{revision}.docx")
    if path.exists() and revision == "auto":
        raise DemoError("AUTO_IMMUTABLE")
    doc = Document()
    doc.core_properties.author = ""
    doc.core_properties.last_modified_by = ""
    section = doc.sections[0]
    section.page_width, section.page_height = Pt(595.28), Pt(841.89)
    section.left_margin = section.right_margin = Pt(45)
    section.top_margin = section.bottom_margin = Pt(40)
    available = 505.28
    spatial = ir["metadata"].get("layout_profile") == "pp_geometry_flow"
    content_left = ir["metadata"].get("content_left_pt", 0)
    font_info = fonts()
    for name, size in [("Normal", 11), ("Title", 16), ("Heading 1", 13), ("Caption", 10)]:
        style: Any = doc.styles[name]
        style.font.name = font_info["latin"] or "Arial"
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.element.get_or_add_rPr().get_or_add_rFonts().set(
            qn("w:eastAsia"), font_info["east_asia"] or "sans-serif"
        )
        style.paragraph_format.space_after = Pt(5)
        if spatial:
            style.paragraph_format.space_before = Pt(0)
            style.paragraph_format.line_spacing = 1.05
    assets = {a["id"]: a for a in ir["assets"]}
    parts = ir["metadata"].get("inline_parts", {})
    counts = {
        "editable_text_char_count": 0,
        "placed_figure_count": 0,
        "formula_image_count": 0,
        "fallback_region_count": 0,
        "omml_formula_count": 0,
    }

    def picture(paragraph: Any, aid: str, width: float, formula: bool = False) -> None:
        if aid not in assets:
            raise DemoError("ASSET_MISSING")
        a = assets[aid]
        source = safe_path(job, a["path"])
        if not source.is_file():
            raise DemoError("ASSET_MISSING")
        with Image.open(source) as im:
            w, h = im.size
        natural = max(1.0, a["source_bbox"][2] - a["source_bbox"][0])
        actual = min(width, natural)
        # Preserve source aspect ratio; bound tall images to printable page height.
        actual = min(actual, 650 * w / h)
        paragraph.add_run().add_picture(str(source), width=Pt(actual))
        if formula:
            counts["formula_image_count"] += 1

    def write_block(parent: Any, b: Json, width: float = available, existing: Any = None) -> None:
        style = (
            "Heading 1"
            if b["type"] == "heading"
            else "Caption"
            if b["type"] in {"caption", "footer"}
            else "Normal"
        )
        para = existing if existing is not None else parent.add_paragraph(style=style)
        para.style = style
        if spatial and b["type"] in {"heading", "footer"}:
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if (
            spatial
            and b["type"] == "paragraph"
            and b["geometry_source"] == "pp_structure"
            and b["bbox"][0] > content_left + 60
        ):
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para.paragraph_format.keep_with_next = b["type"] in {"heading", "caption", "question"}
        para.paragraph_format.widow_control = True
        content = b["content"]
        if content["kind"] == "image":
            picture(para, content["asset_id"], width)
            if b["type"] == "figure":
                counts["placed_figure_count"] += 1
            else:
                counts["fallback_region_count"] += 1
            return
        if b["id"] in parts:
            for item in parts[b["id"]]:
                if "omml" in item:
                    math = etree.fromstring(
                        item["omml"].encode(),
                        etree.XMLParser(resolve_entities=False, no_network=True),
                    )
                    if (
                        math.tag
                        != "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath"
                    ):
                        raise DemoError("INVALID_OMML")
                    para._p.append(math)
                    counts["omml_formula_count"] += 1
                elif "asset_id" in item:
                    picture(para, item["asset_id"], width, True)
                else:
                    if unrendered_math(item["text"]):
                        raise DemoError("UNRENDERED_MATH_REQUIRES_REVIEW")
                    para.add_run(item["text"])
                    counts["editable_text_char_count"] += len(item["text"].strip())
            return
        if content["kind"] != "text":
            raise DemoError("UNSUPPORTED_IR_CONTENT")
        text = content["plain_text"]
        if unrendered_math(text):
            raise DemoError("UNRENDERED_MATH_REQUIRES_REVIEW")
        if content["runs"]:
            for r in content["runs"]:
                run = para.add_run(r["text"])
                run.bold, run.italic = r["bold"], r["italic"]
                if r["font_size_pt"]:
                    run.font.size = Pt(r["font_size_pt"])
                if r["font_family"]:
                    run.font.name = r["font_family"]
        else:
            para.add_run(text)
        counts["editable_text_char_count"] += len(text.strip())

    for p in ir["pages"]:
        decision = ir["metadata"].get("layout_by_page", {}).get(str(p["page_index"]))
        content_left = (
            decision.get("content_left_pt", 0)
            if decision
            else ir["metadata"].get("content_left_pt", 0)
        )
        if decision:
            spatial = decision["status"] == "APPLIED"
        by_id = {b["id"]: b for b in p["blocks"]}
        group_map: dict[str, Json] = {}
        for g in ir["metadata"].get("figure_groups", []):
            if g["page_index"] == p["page_index"]:
                for pair in g["pairs"]:
                    group_map[pair["label"]] = g
                    group_map[pair["figure"]] = g
        text_map: dict[str, Json] = {}
        for g in ir["metadata"].get("text_groups", []):
            if g["page_index"] == p["page_index"]:
                for row in g["rows"]:
                    for item in row:
                        text_map[item] = g
        done: set[str] = set()
        for bid in p["reading_order"]:
            if bid in done:
                continue
            if bid in text_map:
                g = text_map[bid]
                indent = min(g.get("indent_pt", 0), 36)
                width = available - indent
                table = doc.add_table(rows=len(g["rows"]), cols=g["columns"])
                table.autofit = False
                widths = text_column_widths(g["rows"], by_id, width, parts)
                for column, cell_width in zip(table.columns, widths, strict=True):
                    column.width = Pt(cell_width)
                borders = OxmlElement("w:tblBorders")
                for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
                    el = OxmlElement("w:" + edge)
                    el.set(qn("w:val"), "nil")
                    borders.append(el)
                table._tbl.tblPr.append(borders)
                ind = OxmlElement("w:tblInd")
                ind.set(qn("w:w"), str(round(indent * 20)))
                ind.set(qn("w:type"), "dxa")
                table._tbl.tblPr.append(ind)
                for ri, row in enumerate(g["rows"]):
                    table.rows[ri]._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
                    for ci, item in enumerate(row):
                        cell = table.cell(ri, ci)
                        cell.width = Pt(widths[ci])
                        write_block(cell, by_id[item], widths[ci] - 10, cell.paragraphs[0])
                        done.add(item)
                continue
            if bid not in group_map:
                write_block(doc, by_id[bid])
                continue
            g = group_map[bid]
            pairs = g["pairs"]
            cols = min(g.get("columns", 2 if g["kind"] == "option_grid" else 3), len(pairs))
            table = doc.add_table(rows=(len(pairs) + cols - 1) // cols, cols=cols)
            table.autofit = False
            for column in table.columns:
                column.width = Pt(available / cols)
            borders = OxmlElement("w:tblBorders")
            for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
                e = OxmlElement("w:" + edge)
                e.set(qn("w:val"), "nil")
                borders.append(e)
            table._tbl.tblPr.append(borders)
            for row in table.rows:
                prop = row._tr.get_or_add_trPr()
                prop.append(OxmlElement("w:cantSplit"))
            for i, pair in enumerate(pairs):
                cell = table.cell(i // cols, i % cols)
                cell.width = Pt(available / cols)
                if g.get("inline_labels"):
                    label = by_id[pair["label"]]
                    para = cell.paragraphs[0]
                    text = label["content"]["plain_text"]
                    para.add_run(text + " ")
                    counts["editable_text_char_count"] += len(text.strip())
                    picture(
                        para, by_id[pair["figure"]]["content"]["asset_id"], available / cols - 30
                    )
                    counts["placed_figure_count"] += 1
                    para.paragraph_format.space_after = Pt(6)
                else:
                    first, second = (
                        ("label", "figure") if g["kind"] == "option_grid" else ("figure", "label")
                    )
                    write_block(
                        cell,
                        by_id[pair[first]],
                        available / cols - 16,
                        cell.paragraphs[0] if spatial else None,
                    )
                    write_block(cell, by_id[pair[second]], available / cols - 16)
                    cell.paragraphs[-2].paragraph_format.keep_with_next = True
                    cell.paragraphs[-1].paragraph_format.keep_with_next = False
                done.update(pair.values())
    doc.save(str(path))
    path.chmod(0o600)
    return {**counts, "fonts": font_info, **inspect_package(path)}


def inspect_package(path: Path) -> Json:
    """Validate XML, internal relationship targets, editable runs and image extents."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        for name in names:
            if name.endswith((".xml", ".rels")):
                root = etree.fromstring(z.read(name), parser)
                if name.endswith(".rels"):
                    parent = posixpath.dirname(posixpath.dirname(name))
                    for rel in root:
                        target = rel.get("Target", "")
                        if rel.get("TargetMode") == "External":
                            raise DemoError("EXTERNAL_RELATIONSHIP")
                        resolved = posixpath.normpath(posixpath.join(parent, target)).lstrip("/")
                        if resolved not in names:
                            raise DemoError("OOXML_TARGET_MISSING")
            if name.startswith("word/media/"):
                with Image.open(io.BytesIO(z.read(name))) as im:
                    im.verify()
        root = etree.fromstring(z.read("word/document.xml"), parser)
        ns = {
            "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
            "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
            "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
        }
        text = "".join(root.xpath("//w:t/text()", namespaces=ns))
        math_text = "".join(root.xpath("//m:oMath//m:t/text()", namespaces=ns))
        for extent in root.xpath("//wp:extent", namespaces=ns):
            if int(extent.get("cx", "0")) <= 0 or int(extent.get("cy", "0")) <= 0:
                raise DemoError("INVALID_IMAGE_EXTENT")
        return {
            "docx_package_valid": True,
            "has_editable_runs": bool(text.strip() or math_text.strip()),
            "package_text_char_count": len(text),
        }
