"""Read actual OOXML without importing the converter or its QA calculations."""

from __future__ import annotations

import hashlib
import io
import posixpath
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree
from PIL import Image

Json = dict[str, Any]
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
}


def xml(data: bytes) -> Any:
    """Reject DTDs and never resolve entities or fetch resources."""
    root = etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True))
    if root.getroottree().docinfo.doctype:
        raise ValueError("DTD_FORBIDDEN")
    return root


def math_tree(node: Any) -> Any:
    """Canonical OMML structure, excluding styling, never algebraically simplifying."""
    name = etree.QName(node).localname
    namespace = etree.QName(node).namespace
    if name == "rPr" and namespace == NS["w"]:
        return None
    # Only explicit styling exceptions are ignored; fPr/type, delimiters and other
    # mathematical properties must remain visible to the bounded OMML parser.
    if name == "rPr" and all(etree.QName(c).localname == "sty" for c in node):
        return None
    if name == "ctrlPr" and all(etree.QName(c).namespace == NS["w"] for c in node):
        return None
    children = [value for child in node if (value := math_tree(child)) is not None]
    return [name, node.text or "", children]


def table_grid(table: Any) -> Json:
    """Count each physical logical cell once, including gridSpan and vMerge."""
    cells: list[Json] = []
    active: dict[int, Json] = {}
    rows = table.findall("w:tr", NS)
    columns = len(table.findall("w:tblGrid/w:gridCol", NS))
    for ri, row in enumerate(rows):
        before = row.find("w:trPr/w:gridBefore", NS)
        ci = int(before.get(f"{{{NS['w']}}}val", "0")) if before is not None else 0
        current: dict[int, Json] = {}
        for cell in row.findall("w:tc", NS):
            span = cell.find("w:tcPr/w:gridSpan", NS)
            width = int(span.get(f"{{{NS['w']}}}val", "1")) if span is not None else 1
            merge = cell.find("w:tcPr/w:vMerge", NS)
            continuation = merge is not None and merge.get(f"{{{NS['w']}}}val") != "restart"
            if width < 1 or ci + width > columns:
                raise ValueError("INVALID_TABLE_GRID")
            if continuation:
                if cell.xpath(".//w:t/text()", namespaces=NS):
                    raise ValueError("INVALID_TABLE_MERGE")
                parent = active.get(ci)
                if parent is None or parent["colspan"] != width:
                    raise ValueError("INVALID_TABLE_MERGE")
                parent["rowspan"] += 1
                current[ci] = parent
            else:
                item = {
                    "row": ri,
                    "col": ci,
                    "rowspan": 1,
                    "colspan": width,
                    "text": "".join(cell.xpath(".//w:t/text()", namespaces=NS)),
                }
                cells.append(item)
                if merge is not None:
                    current[ci] = item
            ci += width
        active = current
    return {"rows": len(rows), "cols": columns, "cells": cells}


def inspect(path: Path) -> Json:
    """Return body, table, math, image and bookmark evidence with safe error codes."""
    result: Json = {"errors": [], "paragraphs": [], "tables": [], "media_count": 0}
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("DUPLICATE_ZIP_MEMBER")
            if sum(i.file_size for i in archive.infolist()) > 128 * 1024 * 1024:
                raise ValueError("PACKAGE_TOO_LARGE")
            for name in names:
                if name.endswith((".xml", ".rels")):
                    root = xml(archive.read(name))
                    if name.endswith(".rels"):
                        base = posixpath.dirname(posixpath.dirname(name))
                        for rel in root:
                            if rel.get("TargetMode") == "External":
                                raise ValueError("EXTERNAL_RELATIONSHIP")
                            target = posixpath.normpath(posixpath.join(base, rel.get("Target", "")))
                            if target not in names or target.startswith("../"):
                                raise ValueError("MISSING_RELATIONSHIP_TARGET")
                if name.startswith("word/media/"):
                    try:
                        with Image.open(io.BytesIO(archive.read(name))) as image:
                            image.verify()
                    except (OSError, ValueError) as exc:
                        raise ValueError("CORRUPT_MEDIA") from exc
                    result["media_count"] += 1
            relationships = {}
            rel_path = "word/_rels/document.xml.rels"
            if rel_path in names:
                for rel in xml(archive.read(rel_path)):
                    target = posixpath.normpath(posixpath.join("word", rel.get("Target", "")))
                    relationships[rel.get("Id")] = hashlib.sha256(archive.read(target)).hexdigest()
            root = xml(archive.read("word/document.xml"))
            tables = root.xpath("//w:tbl", namespaces=NS)
            for table in tables:
                if table.xpath("ancestor::w:tbl", namespaces=NS):
                    raise ValueError("UNSUPPORTED_NESTED_TABLE")
                result["tables"].append(table_grid(table))
            for paragraph in root.xpath("//w:body//w:p", namespaces=NS):
                parents = paragraph.xpath("ancestor::w:tbl", namespaces=NS)
                result["paragraphs"].append(
                    {
                        "text": "".join(paragraph.xpath(".//w:t/text()", namespaces=NS)),
                        "math": [
                            math_tree(m) for m in paragraph.xpath(".//m:oMath", namespaces=NS)
                        ],
                        "images": [
                            relationships[rid]
                            for rid in paragraph.xpath(".//a:blip/@r:embed", namespaces=NS)
                        ],
                        "markers": paragraph.xpath(".//w:bookmarkStart/@w:name", namespaces=NS),
                        "table": tables.index(parents[-1]) if parents else None,
                    }
                )
            for extent in root.xpath("//wp:extent", namespaces=NS):
                if int(extent.get("cx", "0")) <= 0 or int(extent.get("cy", "0")) <= 0:
                    raise ValueError("INVALID_IMAGE_EXTENT")
    except (zipfile.BadZipFile, KeyError, etree.XMLSyntaxError, ValueError, OSError) as exc:
        known = {
            "DUPLICATE_ZIP_MEMBER",
            "PACKAGE_TOO_LARGE",
            "EXTERNAL_RELATIONSHIP",
            "MISSING_RELATIONSHIP_TARGET",
            "CORRUPT_MEDIA",
            "INVALID_IMAGE_EXTENT",
            "UNSUPPORTED_NESTED_TABLE",
            "INVALID_TABLE_GRID",
            "INVALID_TABLE_MERGE",
            "DTD_FORBIDDEN",
        }
        code = str(exc) if str(exc) in known else type(exc).__name__.upper()
        result["errors"].append(code)
    return result
