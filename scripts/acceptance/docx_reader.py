"""Read actual OOXML without importing the converter or its QA calculations."""

from __future__ import annotations

import hashlib
import io
import posixpath
import re
import zipfile
from pathlib import Path
from typing import Any

from docx.opc.constants import CONTENT_TYPE as CT
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


UNSUPPORTED_WORD_CONTENT = [
    "sym",
    "altChunk",
    "pict",
    "object",
    "contentPart",
    "fldSimple",
    "instrText",
    "noBreakHyphen",
    "softHyphen",
    "txbxContent",
    "footnoteReference",
    "endnoteReference",
]


WORD_PART_TYPES = {
    NS["r"] + "/" + name: content_type
    for name, content_type in {
        "styles": CT.WML_STYLES,
        "header": CT.WML_HEADER,
        "footer": CT.WML_FOOTER,
        "footnotes": CT.WML_FOOTNOTES,
        "endnotes": CT.WML_ENDNOTES,
        "numbering": CT.WML_NUMBERING,
        "settings": CT.WML_SETTINGS,
        "fontTable": CT.WML_FONT_TABLE,
        "webSettings": CT.WML_WEB_SETTINGS,
        "comments": CT.WML_COMMENTS,
        "theme": CT.OFC_THEME,
    }.items()
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
    default_properties = {"fPr": {"type": "bar"}, "sSupPr": {}, "sSubPr": {}, "sSubSupPr": {}}
    if namespace == NS["m"] and name in default_properties and not node.attrib:
        # Office writes explicit defaults and control styling on ordinary math.
        # Keep unknown/non-default properties visible (notably noBar and skw).
        allowed = default_properties[name]
        defaults_only = True
        for child in node:
            child_name = etree.QName(child).localname
            if (
                etree.QName(child).namespace == NS["m"]
                and child_name == "ctrlPr"
                and math_tree(child) is None
            ):
                continue
            if (
                etree.QName(child).namespace != NS["m"]
                or child_name not in allowed
                or dict(child.attrib) != {f"{{{NS['m']}}}val": allowed[child_name]}
                or len(child)
            ):
                defaults_only = False
                break
        if defaults_only:
            return None
    children = [value for child in node if (value := math_tree(child)) is not None]
    return [name, node.text or "", children]


def word_text(node: Any) -> str:
    """Read Word run text and inline controls in order, excluding tab-stop formatting."""
    pieces = []
    for item in node.xpath(".//w:r/w:t | .//w:r/w:tab | .//w:r/w:br | .//w:r/w:cr", namespaces=NS):
        name = etree.QName(item).localname
        if name == "t":
            pieces.append(item.text or "")
        elif name == "tab":
            pieces.append("\t")
        elif name == "cr":
            pieces.append("\n")
        else:
            kind = item.get(f"{{{NS['w']}}}type", "textWrapping")
            if kind not in {"textWrapping", "page", "column"}:
                raise ValueError("UNSUPPORTED_TEXT_BREAK")
            pieces.append({"textWrapping": "\n", "page": "\f", "column": "\v"}[kind])
    return "".join(pieces)


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
                    "text": "\n".join(word_text(p) for p in cell.xpath(".//w:p", namespaces=NS)),
                    "has_content": bool(
                        word_text(cell).strip()
                        or cell.xpath(".//m:oMath | .//a:blip", namespaces=NS)
                    ),
                }
                cells.append(item)
                if merge is not None:
                    current[ci] = item
            ci += width
        active = current
    borders = table.find("w:tblPr/w:tblBorders", NS)
    edge_names = {"top", "left", "bottom", "right", "insideH", "insideV"}
    borderless = borders is not None and all(
        (edge := borders.find("w:" + name, NS)) is not None
        and edge.get(f"{{{NS['w']}}}val") in {"nil", "none"}
        for name in edge_names
    )
    cell_borders = table.xpath(".//w:tcPr/w:tcBorders/*", namespaces=NS)
    borderless = borderless and all(
        b.get(f"{{{NS['w']}}}val") in {"nil", "none"} for b in cell_borders
    )
    return {"rows": len(rows), "cols": columns, "cells": cells, "borderless": borderless}


def _check_opc(archive: zipfile.ZipFile, names: list[str]) -> dict[str, str]:
    """Require the OPC declarations and supported Word main-document relationship."""
    if not {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}.issubset(names):
        raise ValueError("OPC_REQUIRED_PART_MISSING")
    types = xml(archive.read("[Content_Types].xml"))
    rels = xml(archive.read("_rels/.rels"))
    ct_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    if types.tag != f"{{{ct_ns}}}Types" or rels.tag != f"{{{rel_ns}}}Relationships":
        raise ValueError("OPC_INVALID_DECLARATION")
    main = [
        r
        for r in rels
        if r.tag == f"{{{rel_ns}}}Relationship" and r.get("Type") == NS["r"] + "/officeDocument"
    ]
    if (
        len(main) != 1
        or main[0].get("TargetMode") == "External"
        or posixpath.normpath(main[0].get("Target", "")).lstrip("/") != "word/document.xml"
    ):
        raise ValueError("OPC_MAIN_RELATIONSHIP_INVALID")
    overrides = {
        n.get("PartName"): n.get("ContentType") for n in types if n.tag == f"{{{ct_ns}}}Override"
    }
    defaults = {
        (n.get("Extension") or "").lower(): n.get("ContentType")
        for n in types
        if n.tag == f"{{{ct_ns}}}Default"
    }
    main_type = overrides.get("/word/document.xml", defaults.get("xml"))
    if (
        main_type
        != "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
    ):
        raise ValueError("OPC_MAIN_CONTENT_TYPE_INVALID")
    document = xml(archive.read("word/document.xml"))
    if document.tag != f"{{{NS['w']}}}document" or len(document.findall("w:body", NS)) != 1:
        raise ValueError("OPC_MAIN_DOCUMENT_INVALID")
    part_types: dict[str, str] = {}
    for name in names:
        if name == "[Content_Types].xml" or name.endswith("/"):
            continue
        extension = name.rsplit("/", 1)[-1].rsplit(".", 1)[-1].lower()
        content_type = overrides.get("/" + name, defaults.get(extension))
        if not content_type:
            raise ValueError("OPC_PART_CONTENT_TYPE_MISSING")
        media_type = content_type.split(";", 1)[0]
        mime_token = r"[!#$%&'*+.^_`|~0-9A-Za-z-]+"
        if not re.fullmatch(mime_token + '/' + mime_token, media_type):
            raise ValueError("OPC_PART_CONTENT_TYPE_INVALID")
        if name.endswith(".rels") and content_type != CT.OPC_RELATIONSHIPS:
            raise ValueError("OPC_RELATIONSHIPS_CONTENT_TYPE_INVALID")
        part_types[name] = content_type
    return part_types


def _hidden_content(document: Any, styles: Any) -> bool:
    """Resolve vanish through defaults and used paragraph/character style chains."""
    val = f"{{{NS['w']}}}val"
    style_map = {s.get(f"{{{NS['w']}}}styleId"): s for s in styles.findall("w:style", NS)}

    def enabled(node: Any) -> bool:
        value = node.get(val, "true")
        if value not in {"0", "false", "off", "1", "true", "on"}:
            raise ValueError("INVALID_VISIBILITY_PROPERTY")
        return value in {"1", "true", "on"}

    default_node = styles.find("w:docDefaults/w:rPrDefault/w:rPr/w:vanish", NS)
    default_hidden = enabled(default_node) if default_node is not None else False
    defaults = {
        s.get(f"{{{NS['w']}}}type"): sid
        for sid, s in style_map.items()
        if s.get(f"{{{NS['w']}}}default") in {"1", "true", "on"}
    }

    def apply_style(hidden: bool, sid: str | None) -> bool:
        chain = []
        seen = set()
        while sid in style_map:
            if sid in seen:
                raise ValueError("UNSUPPORTED_VISIBILITY_STYLE")
            seen.add(sid)
            style = style_map[sid]
            chain.append(style)
            parent = style.find("w:basedOn", NS)
            sid = parent.get(val) if parent is not None else None
        for style in reversed(chain):
            if any(enabled(v) for v in style.findall(".//w:tblStylePr/w:rPr/w:vanish", NS)):
                raise ValueError("UNSUPPORTED_VISIBILITY_STYLE")
            vanish = style.find("w:rPr/w:vanish", NS)
            # In styles, enabled toggle properties invert the inherited setting;
            # explicit run formatting below sets an absolute on/off value.
            if vanish is not None and enabled(vanish):
                hidden = not hidden
        return hidden

    for paragraph in document.xpath("//w:body//w:p", namespaces=NS):
        pstyle = paragraph.find("w:pPr/w:pStyle", NS)
        table_hidden = default_hidden
        tables = paragraph.xpath("ancestor::w:tbl", namespaces=NS)
        if tables:
            table_style = tables[-1].find("w:tblPr/w:tblStyle", NS)
            table_hidden = apply_style(
                default_hidden,
                table_style.get(val) if table_style is not None else defaults.get("table"),
            )
        inherited = apply_style(
            table_hidden, pstyle.get(val) if pstyle is not None else defaults.get("paragraph")
        )
        for run in paragraph.xpath(".//w:r | .//m:r", namespaces=NS):
            rstyle = run.find("w:rPr/w:rStyle", NS)
            hidden = apply_style(
                inherited, rstyle.get(val) if rstyle is not None else defaults.get("character")
            )
            direct = run.find("w:rPr/w:vanish", NS)
            if direct is not None:
                hidden = enabled(direct)
            payload = "".join(
                run.xpath("./w:t/text() | ./m:t/text()", namespaces=NS)
            ).strip() or run.xpath(
                "./w:tab | ./w:br | ./w:cr | ./w:drawing | ./w:sym | ./w:pict", namespaces=NS
            )
            if hidden and payload:
                return True
    return False


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
            content_types = _check_opc(archive, names)
            for name in names:
                if name.endswith("/"):
                    continue
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
                            expected_type = WORD_PART_TYPES.get(rel.get("Type", ""))
                            if expected_type and content_types.get(target) != expected_type:
                                raise ValueError("OPC_WORD_CONTENT_TYPE_INVALID")
                if name.startswith("word/media/"):
                    try:
                        with Image.open(io.BytesIO(archive.read(name))) as image:
                            image.verify()
                    except (OSError, ValueError) as exc:
                        raise ValueError("CORRUPT_MEDIA") from exc
                    result["media_count"] += 1
            relationships = {}
            styles_target: str | None = None
            story_relationships: list[tuple[str, str, str]] = []
            rel_path = "word/_rels/document.xml.rels"
            if rel_path in names:
                for rel in xml(archive.read(rel_path)):
                    target = posixpath.normpath(posixpath.join("word", rel.get("Target", "")))
                    if rel.get("Type") == NS["r"] + "/image":
                        data = archive.read(target)
                        with Image.open(io.BytesIO(data)) as picture:
                            actual_type = Image.MIME.get(picture.format or "")
                            picture.verify()
                        if actual_type is None or content_types.get(target) != actual_type:
                            raise ValueError("IMAGE_CONTENT_TYPE_INVALID")
                        relationships[rel.get("Id")] = hashlib.sha256(data).hexdigest()
                    kind = rel.get("Type", "").rsplit("/", 1)[-1]
                    if kind == "styles":
                        if styles_target is not None:
                            raise ValueError("OPC_STYLE_RELATIONSHIP_INVALID")
                        styles_target = target
                    if kind in {"header", "footer", "footnotes", "endnotes"}:
                        story_relationships.append((rel.get("Id", ""), kind, target))
            root = xml(archive.read("word/document.xml"))
            if any(
                rid not in relationships for rid in root.xpath("//a:blip/@r:embed", namespaces=NS)
            ):
                raise ValueError("INVALID_IMAGE_RELATIONSHIP")
            styles = (
                xml(archive.read(styles_target))
                if styles_target is not None
                else etree.Element(f"{{{NS['w']}}}styles")
            )
            if _hidden_content(root, styles):
                result["errors"].append("HIDDEN_CONTENT")
            referenced_stories = set(
                root.xpath("//w:headerReference/@r:id | //w:footerReference/@r:id", namespaces=NS)
            )
            for rid, kind, target in story_relationships:
                referenced = rid in referenced_stories or (
                    kind in {"footnotes", "endnotes"}
                    and bool(root.xpath("//w:" + kind[:-1] + "Reference", namespaces=NS))
                )
                if not referenced:
                    continue
                story = xml(archive.read(target))
                text = word_text(story)
                visible = story.xpath(
                    "//m:oMath | //w:drawing | //a:blip | "
                    + " | ".join("//w:" + tag for tag in UNSUPPORTED_WORD_CONTENT),
                    namespaces=NS,
                )
                if text or visible:
                    result["errors"].append("UNSUPPORTED_VISIBLE_STORY")
            if root.xpath("//w:body//a:blip[@r:link]", namespaces=NS):
                result["errors"].append("UNSUPPORTED_LINKED_IMAGE")
            unsupported_body = root.xpath(
                " | ".join("//w:body//w:" + tag for tag in UNSUPPORTED_WORD_CONTENT), namespaces=NS
            )
            unknown_drawings = root.xpath(
                "//w:body//w:drawing[not(.//a:blip)] | //w:body//a:t", namespaces=NS
            )
            if unsupported_body or unknown_drawings:
                result["errors"].append("UNSUPPORTED_BODY_CONTENT")
            tables = root.xpath("//w:tbl", namespaces=NS)
            for table in tables:
                if table.xpath("ancestor::w:tbl", namespaces=NS):
                    raise ValueError("UNSUPPORTED_NESTED_TABLE")
                result["tables"].append(table_grid(table))
            for paragraph in root.xpath("//w:body//w:p", namespaces=NS):
                parents = paragraph.xpath("ancestor::w:tbl", namespaces=NS)
                result["paragraphs"].append(
                    {
                        "text": word_text(paragraph),
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
            "UNSUPPORTED_TEXT_BREAK",
            "OPC_REQUIRED_PART_MISSING",
            "OPC_INVALID_DECLARATION",
            "OPC_MAIN_RELATIONSHIP_INVALID",
            "OPC_MAIN_CONTENT_TYPE_INVALID",
            "OPC_MAIN_DOCUMENT_INVALID",
            "OPC_STYLE_RELATIONSHIP_INVALID",
            "INVALID_VISIBILITY_PROPERTY",
            "UNSUPPORTED_VISIBILITY_STYLE",
            "INVALID_IMAGE_RELATIONSHIP",
            "IMAGE_CONTENT_TYPE_INVALID",
            "OPC_PART_CONTENT_TYPE_MISSING",
            "OPC_PART_CONTENT_TYPE_INVALID",
            "OPC_RELATIONSHIPS_CONTENT_TYPE_INVALID",
            "OPC_WORD_CONTENT_TYPE_INVALID",
        }
        code = str(exc) if str(exc) in known else type(exc).__name__.upper()
        result["errors"].append(code)
    return result
