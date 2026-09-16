"""Read actual OOXML without importing the converter or its QA calculations."""

from __future__ import annotations

import hashlib
import io
import posixpath
import re
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
}


UNSUPPORTED_WORD_CONTENT = [
    "sym",
    "ptab",
    "pgNum",
    "dayLong",
    "dayShort",
    "monthLong",
    "monthShort",
    "yearLong",
    "yearShort",
    "commentReference",
    "commentRangeStart",
    "commentRangeEnd",
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


REVISION_ELEMENTS = {
    "ins",
    "del",
    "moveFrom",
    "moveTo",
    "moveFromRangeStart",
    "moveFromRangeEnd",
    "moveToRangeStart",
    "moveToRangeEnd",
    "rPrChange",
    "pPrChange",
    "sectPrChange",
    "tblPrChange",
    "tblPrExChange",
    "tblGridChange",
    "trPrChange",
    "tcPrChange",
    "numberingChange",
    "cellIns",
    "cellDel",
    "cellMerge",
    "delText",
    "delInstrText",
    "customXmlInsRangeStart",
    "customXmlInsRangeEnd",
    "customXmlDelRangeStart",
    "customXmlDelRangeEnd",
    "customXmlMoveFromRangeStart",
    "customXmlMoveFromRangeEnd",
    "customXmlMoveToRangeStart",
    "customXmlMoveToRangeEnd",
}


def _has_revisions(part: Any) -> bool:
    """Do not infer a final/original/markup view for pending revision content."""
    conflicts = {
        "conflictIns",
        "conflictDel",
        "customXmlConflictInsRangeStart",
        "customXmlConflictInsRangeEnd",
        "customXmlConflictDelRangeStart",
        "customXmlConflictDelRangeEnd",
    }
    for node in part.iter():
        if not isinstance(node.tag, str):
            continue
        name = etree.QName(node)
        if (name.namespace == NS["w"] and name.localname in REVISION_ELEMENTS) or (
            name.namespace == "http://schemas.microsoft.com/office/word/2010/wordml"
            and name.localname in conflicts
        ):
            return True
    return False


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
    children_nodes = [child for child in node if isinstance(child.tag, str)]
    if name == "rPr" and namespace == NS["w"]:
        parent = node.getparent()
        if parent is None or parent.tag not in {f"{{{NS['m']}}}r", f"{{{NS['m']}}}ctrlPr"}:
            raise ValueError("INVALID_OMML_NAMESPACE")
        return None
    if namespace != NS["m"]:
        raise ValueError("INVALID_OMML_NAMESPACE")
    if name == "phant":
        raise ValueError("UNSUPPORTED_OMML_VISIBILITY")
    if name == "t" and children_nodes:
        raise ValueError("INVALID_OMML_STRUCTURE")
    # Only explicit styling exceptions are ignored; fPr/type, delimiters and other
    # mathematical properties must remain visible to the bounded OMML parser.
    if name == "rPr" and all(c.tag == f"{{{NS['m']}}}sty" for c in children_nodes):
        return None
    if name == "ctrlPr" and all(c.tag == f"{{{NS['w']}}}rPr" for c in children_nodes):
        return None
    default_properties = {"fPr": {"type": "bar"}, "sSupPr": {}, "sSubPr": {}, "sSubSupPr": {}}
    if namespace == NS["m"] and name in default_properties and not node.attrib:
        # Office writes explicit defaults and control styling on ordinary math.
        # Keep unknown/non-default properties visible (notably noBar and skw).
        allowed = default_properties[name]
        defaults_only = True
        for child in children_nodes:
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
                or any(isinstance(c.tag, str) for c in child)
            ):
                defaults_only = False
                break
        if defaults_only:
            return None
    children = [value for child in children_nodes if (value := math_tree(child)) is not None]
    return [name, "".join(node.itertext()) if name == "t" else node.text or "", children]


def word_text(node: Any) -> str:
    """Read Word run text and inline controls in order, excluding tab-stop formatting."""
    pieces = []
    for item in node.xpath(".//w:r/w:t | .//w:r/w:tab | .//w:r/w:br | .//w:r/w:cr", namespaces=NS):
        name = etree.QName(item).localname
        if name == "t":
            if any(isinstance(child.tag, str) for child in item):
                raise ValueError("INVALID_WORD_TEXT")
            pieces.append("".join(item.itertext()))
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
    if table.find(".//w:tcPr/w:hMerge", NS) is not None:
        raise ValueError("UNSUPPORTED_HORIZONTAL_MERGE")
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
                if word_text(cell) or cell.xpath(".//m:oMath | .//w:drawing", namespaces=NS):
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


def _part_target(base: str, target: str) -> str:
    """Resolve an internal package path, rejecting traversal above package root."""
    uri = urlsplit(target)
    if uri.scheme or uri.netloc or uri.query or uri.fragment or "\\" in target:
        raise ValueError("MISSING_RELATIONSHIP_TARGET")
    parts = [] if target.startswith("/") else [p for p in base.split("/") if p]
    for part in target.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise ValueError("MISSING_RELATIONSHIP_TARGET")
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


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
        or _part_target("", main[0].get("Target", "")) != "word/document.xml"
    ):
        raise ValueError("OPC_MAIN_RELATIONSHIP_INVALID")
    override_keys = [n.get("PartName") for n in types if n.tag == f"{{{ct_ns}}}Override"]
    default_keys = [
        (n.get("Extension") or "").lower() for n in types if n.tag == f"{{{ct_ns}}}Default"
    ]
    if len(set(override_keys)) != len(override_keys) or len(set(default_keys)) != len(default_keys):
        raise ValueError("OPC_DUPLICATE_CONTENT_TYPE")
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
        if not re.fullmatch(mime_token + "/" + mime_token, media_type):
            raise ValueError("OPC_PART_CONTENT_TYPE_INVALID")
        if name.endswith(".rels") and content_type != CT.OPC_RELATIONSHIPS:
            raise ValueError("OPC_RELATIONSHIPS_CONTENT_TYPE_INVALID")
        part_types[name] = content_type
    return part_types


def _check_bookmarks(document: Any) -> None:
    """Require unique, paired source markers in document order."""
    starts: dict[int, Any] = {}
    ended: set[int] = set()
    names: set[str] = set()
    for node in document.xpath(".//w:bookmarkStart | .//w:bookmarkEnd", namespaces=NS):
        value = node.get(f"{{{NS['w']}}}id", "")
        if not re.fullmatch(r"[0-9]+", value):
            raise ValueError("INVALID_BOOKMARK")
        identifier = int(value)
        if node.tag == f"{{{NS['w']}}}bookmarkStart":
            name = node.get(f"{{{NS['w']}}}name", "")
            if not name or name in names or identifier in starts:
                raise ValueError("INVALID_BOOKMARK")
            names.add(name)
            starts[identifier] = node
        elif identifier not in starts or identifier in ended:
            raise ValueError("INVALID_BOOKMARK")
        else:
            ended.add(identifier)
    if starts.keys() != ended:
        raise ValueError("INVALID_BOOKMARK")


def _check_extension_wrappers(document: Any) -> None:
    """Reject unimplemented extension ancestry before extracting Word payloads."""
    supported = {NS[key] for key in ("w", "m", "a", "wp", "pic")}
    for payload in document.xpath(
        "//w:body//w:p | //w:body//w:r | //w:body//w:t | //w:body//m:oMath | //w:body//a:blip",
        namespaces=NS,
    ):
        for ancestor in payload.iterancestors():
            if etree.QName(ancestor).namespace not in supported:
                raise ValueError("UNSUPPORTED_MARKUP_COMPATIBILITY")


def _check_payload_structure(document: Any) -> None:
    """Validate supported parent chains rather than accepting all WordML descendants."""
    def w(name: str) -> str:
        return f"{{{NS['w']}}}" + name

    allowed = {
        w("p"): {w("body"), w("tc"), w("sdtContent")},
        w("r"): {w("p"), w("hyperlink"), w("sdtContent")},
        w("t"): {w("r")},
        w("drawing"): {w("r")},
        w("hyperlink"): {w("p"), w("sdtContent")},
        w("sdtContent"): {w("sdt")},
        w("sdt"): {w("body"), w("tc"), w("p"), w("hyperlink"), w("sdtContent"), w("tr"), w("tbl")},
        w("tbl"): {w("body"), w("tc"), w("sdtContent")},
        w("tr"): {w("tbl"), w("sdtContent")},
        w("tc"): {w("tr"), w("sdtContent")},
        f"{{{NS['m']}}}oMath": {w("p"), f"{{{NS['m']}}}oMathPara"},
        f"{{{NS['m']}}}oMathPara": {w("p")},
    }
    for payload in document.xpath(
        "//w:body//w:p | //w:body//w:r | //w:body//w:t | //w:body//w:drawing | //w:body//m:oMath",
        namespaces=NS,
    ):
        if payload.xpath("ancestor::m:oMath", namespaces=NS):
            continue  # Math internals retain the independent OMML validator.
        if payload.tag == f"{{{NS['m']}}}oMath" and not payload.xpath(
            "ancestor::w:p", namespaces=NS
        ):
            continue  # The separate block-math check returns its established error.
        node = payload
        while node.tag != w("body"):
            parent = node.getparent()
            if parent is None or parent.tag not in allowed.get(node.tag, set()):
                raise ValueError("INVALID_WORD_STRUCTURE")
            node = parent


def _body_regions(document: Any) -> list[tuple[int, int, int, int]]:
    """Return validated usable section width/height and lateral margins in twips."""
    regions = []
    for section in document.findall(".//w:sectPr", NS) or [None]:
        size = section.find("w:pgSz", NS) if section is not None else None
        margins = section.find("w:pgMar", NS) if section is not None else None

        def number(node: Any, name: str, default: int) -> int:
            try:
                return (
                    int(node.get(f"{{{NS['w']}}}" + name, str(default)))
                    if node is not None else default
                )
            except ValueError as exc:
                raise ValueError("UNSUPPORTED_TEXT_POSITION") from exc

        width, height = number(size, "w", 12240), number(size, "h", 15840)
        left, right = number(margins, "left", 1440), number(margins, "right", 1440)
        top, bottom = number(margins, "top", 1440), number(margins, "bottom", 1440)
        gutter = number(margins, "gutter", 0)
        usable_width, usable_height = width - left - right - gutter, height - top - bottom - gutter
        if min(left, right, top, bottom, gutter) < 0 or min(usable_width, usable_height) < 240:
            raise ValueError("UNSUPPORTED_TEXT_POSITION")
        regions.append((usable_width, usable_height, left, right))
    return regions


def _hidden_content(document: Any, styles: Any, font_table: Any, theme: Any) -> bool:
    """Resolve vanish through defaults and used paragraph/character style chains."""
    val = f"{{{NS['w']}}}val"
    style_map = {s.get(f"{{{NS['w']}}}styleId"): s for s in styles.findall("w:style", NS)}

    def enabled(node: Any) -> bool:
        value = node.get(val, "true")
        if value not in {"0", "false", "off", "1", "true", "on"}:
            raise ValueError("INVALID_VISIBILITY_PROPERTY")
        return value in {"1", "true", "on"}

    def font_key(name: str) -> str:
        return "".join(name.casefold().split())

    symbol_fonts = {
        "symbol", "wingdings", "wingdings2", "wingdings3", "webdings", "zapfdingbats", "mtextra"
    }
    for font in font_table.findall("w:font", NS):
        charset = font.find("w:charset", NS)
        alternate = font.find("w:altName", NS)
        embedded = any(
            font.find("w:" + tag, NS) is not None
            for tag in ("embedRegular", "embedBold", "embedItalic", "embedBoldItalic")
        )
        if embedded or (charset is not None and charset.get(val, "").lower() in {"2", "02"}) or (
            alternate is not None and font_key(alternate.get(val, "")) in symbol_fonts
        ):
            symbol_fonts.add(font_key(font.get(f"{{{NS['w']}}}name", "")))

    def check_font(name: str) -> None:
        if font_key(name) in symbol_fonts:
            raise ValueError("UNSUPPORTED_FONT_MAPPING")

    def check_theme_font(name: str) -> None:
        match = re.fullmatch(r"(major|minor)(Ascii|HAnsi|EastAsia|Bidi)", name)
        if match is None or theme is None:
            raise ValueError("UNSUPPORTED_FONT_MAPPING")
        group = theme.find("a:themeElements/a:fontScheme/a:" + match[1] + "Font", NS)
        kind = {"Ascii": "latin", "HAnsi": "latin", "EastAsia": "ea", "Bidi": "cs"}[match[2]]
        face = group.find("a:" + kind, NS) if group is not None else None
        if face is None:
            raise ValueError("UNSUPPORTED_FONT_MAPPING")
        if face.get("typeface"):
            check_font(face.get("typeface"))
        else:
            for fallback in group.findall("a:font", NS):
                check_font(fallback.get("typeface", ""))

    indent_bound = 1800
    hanging_bound = 1440
    tab_bound = 4680
    body_width = 9360
    for width, _, left, right in _body_regions(document):
        indent_bound = min(indent_bound, width // 4)
        hanging_bound = min(hanging_bound, left, right, indent_bound)
        tab_bound = min(tab_bound, width // 2)
        body_width = min(body_width, width)

    def table_width(node: Any, available: int) -> int:
        raw = node.get(f"{{{NS['w']}}}w", "")
        kind = node.get(f"{{{NS['w']}}}type", "dxa")
        if not re.fullmatch(r"[0-9]+", raw) or kind not in {"dxa", "pct", "auto", "nil"}:
            raise ValueError("UNSUPPORTED_TABLE_WIDTH")
        value = int(raw)
        if kind in {"auto", "nil"}:
            return 0
        width = value * available // 5000 if kind == "pct" else value
        if width > available:
            raise ValueError("UNSUPPORTED_TABLE_WIDTH")
        return width

    cell_width_bound = body_width
    for table in document.xpath("//w:body//w:tbl", namespaces=NS):
        indent = table.find("w:tblPr/w:tblInd", NS)
        try:
            offset = table_width(indent, body_width) if indent is not None else 0
        except ValueError as exc:
            raise ValueError("UNSUPPORTED_TEXT_POSITION") from exc
        if offset > indent_bound:
            raise ValueError("UNSUPPORTED_TEXT_POSITION")
        available = body_width - offset
        grid_widths = [
            table_width(col, available) for col in table.findall("w:tblGrid/w:gridCol", NS)
        ]
        cell_width_bound = min(cell_width_bound, min(grid_widths, default=body_width))
        if sum(grid_widths) > available:
            raise ValueError("UNSUPPORTED_TABLE_WIDTH")
        for declared in table.findall("w:tblPr/w:tblW", NS):
            table_width(declared, available)
        for row in table.findall("w:tr", NS):
            if sum(
                table_width(cell, available) for cell in row.findall("w:tc/w:tcPr/w:tcW", NS)
            ) > available:
                raise ValueError("UNSUPPORTED_TABLE_WIDTH")

    def check_background(properties: Any) -> None:
        if properties is None:
            return
        if any(
            isinstance(node.tag, str) and etree.QName(node).namespace != NS["w"]
            for node in properties.iterdescendants()
        ):
            raise ValueError("UNSUPPORTED_VISIBILITY_STYLE")
        for margins in properties.xpath(".//w:tcMar | .//w:tblCellMar", namespaces=NS):
            for side in margins:
                if not isinstance(side.tag, str):
                    continue
                raw = side.get(f"{{{NS['w']}}}w", "")
                kind = side.get(f"{{{NS['w']}}}type", "dxa")
                bound = min(180, cell_width_bound // 4)
                if (
                    kind not in {"dxa", "nil"}
                    or not re.fullmatch(r"[0-9]+", raw)
                    or int(raw) > (bound if kind == "dxa" else 0)
                ):
                    raise ValueError("UNSUPPORTED_CELL_MARGINS")
        if any(
            enabled(node)
            for node in properties.xpath(".//w:tcFitText | .//w:noWrap", namespaces=NS)
        ):
            raise ValueError("UNSUPPORTED_TEXT_POSITION")
        if properties.find(".//w:tblpPr", NS) is not None:
            raise ValueError("UNSUPPORTED_TEXT_POSITION")
        for tab in properties.findall(".//w:tabs/w:tab", NS):
            if tab.get(val) == "clear":
                continue
            position = tab.get(f"{{{NS['w']}}}pos", "")
            if not re.fullmatch(r"[0-9]+", position) or int(position) > tab_bound:
                raise ValueError("UNSUPPORTED_TEXT_POSITION")
        for declared in properties.xpath(".//w:tblW | .//w:tcW", namespaces=NS):
            table_width(declared, body_width)
        for indent in properties.findall(".//w:tblInd", NS):
            raw = indent.get(f"{{{NS['w']}}}w", "0")
            kind = indent.get(f"{{{NS['w']}}}type", "dxa")
            if (
                not re.fullmatch(r"[0-9]+", raw)
                or kind not in {"dxa", "nil", "auto"}
                or int(raw) > (indent_bound if kind == "dxa" else 0)
            ):
                raise ValueError("UNSUPPORTED_TEXT_POSITION")
        for indent in properties.findall(".//w:ind", NS):
            for key, raw in indent.attrib.items():
                name = etree.QName(key).localname
                limit = hanging_bound if name == "hanging" else indent_bound
                if name not in {"left", "right", "start", "end", "firstLine", "hanging"}:
                    limit = 0
                if not re.fullmatch(r"[0-9]+", raw) or int(raw) > limit:
                    raise ValueError("UNSUPPORTED_TEXT_POSITION")
        if properties.find(".//w:framePr", NS) is not None:
            raise ValueError("UNSUPPORTED_TEXT_POSITION")
        if properties.find(".//w:bdo", NS) is not None:
            raise ValueError("UNSUPPORTED_BIDI_OVERRIDE")
        for fonts in properties.findall(".//w:rFonts", NS):
            for key, name in fonts.attrib.items():
                attribute = etree.QName(key).localname
                if attribute.lower().endswith("theme"):
                    check_theme_font(name)
                elif attribute in {"ascii", "hAnsi", "eastAsia", "cs"}:
                    check_font(name)
        for spacing in properties.findall(".//w:spacing", NS):
            if spacing.getparent().tag == f"{{{NS['w']}}}rPr" and spacing.get(val) != "0":
                raise ValueError("UNSUPPORTED_TEXT_POSITION")
            if spacing.getparent().tag == f"{{{NS['w']}}}pPr":
                rule = spacing.get(f"{{{NS['w']}}}lineRule", "auto")
                line = spacing.get(f"{{{NS['w']}}}line", "240")
                if (
                    rule not in {"auto", "atLeast"}
                    or not re.fullmatch(r"[0-9]+", line)
                    or int(line) < (240 if rule == "auto" else 1)
                ):
                    raise ValueError("UNSUPPORTED_LINE_HEIGHT")
        for effect in properties.xpath(".//w:caps | .//w:smallCaps", namespaces=NS):
            if enabled(effect):
                raise ValueError("UNSUPPORTED_TEXT_CASE")
        for width in properties.findall(".//w:w", NS):
            if width.get(val) != "100":
                raise ValueError("UNSUPPORTED_TEXT_POSITION")
        if properties.find(".//w:fitText", NS) is not None:
            raise ValueError("UNSUPPORTED_TEXT_POSITION")
        for height in properties.findall(".//w:trHeight", NS):
            if height.get(f"{{{NS['w']}}}hRule", "auto") not in {"auto", "atLeast"}:
                raise ValueError("UNSUPPORTED_ROW_HEIGHT")
        for position in properties.findall(".//w:position", NS):
            if position.get(val) != "0":
                raise ValueError("UNSUPPORTED_TEXT_POSITION")
        for size in properties.xpath(".//w:sz | .//w:szCs", namespaces=NS):
            value = size.get(val, "")
            if not re.fullmatch(r"[0-9]+", value) or int(value) < 12:
                raise ValueError("UNSUPPORTED_FONT_SCALE")
        for color in properties.findall(".//w:color", NS):
            if color.get(val) not in {"auto", "000000"} or any(
                "theme" in etree.QName(key).localname.lower() for key in color.attrib
            ):
                raise ValueError("UNSUPPORTED_VISIBILITY_STYLE")
        for node in properties.xpath(".//w:shd | .//w:highlight", namespaces=NS):
            if node.tag == f"{{{NS['w']}}}highlight":
                if node.get(val) == "none":
                    continue
            elif node.get(val) == "nil" or (
                node.get(val, "clear") == "clear"
                and node.get(f"{{{NS['w']}}}fill", "auto") == "auto"
                and not any("theme" in etree.QName(key).localname.lower() for key in node.attrib)
            ):
                continue
            # Background/theme/pattern rendering needs a renderer to establish contrast.
            raise ValueError("UNSUPPORTED_VISIBILITY_STYLE")

    background = document.find("w:background", NS)
    if background is not None and (
        background.get(f"{{{NS['w']}}}color") != "FFFFFF"
        or any("theme" in etree.QName(key).localname.lower() for key in background.attrib)
        or len(background)
    ):
        raise ValueError("UNSUPPORTED_VISIBILITY_STYLE")
    check_background(styles.find("w:docDefaults", NS))
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
            check_background(style)
            if any(enabled(node) for node in style.findall(".//w:trPr/w:hidden", NS)):
                raise ValueError("UNSUPPORTED_VISIBILITY_STYLE")
            if any(enabled(v) for v in style.findall(".//w:tblStylePr/w:rPr/w:vanish", NS)):
                raise ValueError("UNSUPPORTED_VISIBILITY_STYLE")
            vanish = style.find("w:rPr/w:vanish", NS)
            # In styles, enabled toggle properties invert the inherited setting;
            # explicit run formatting below sets an absolute on/off value.
            if vanish is not None and enabled(vanish):
                hidden = not hidden
        return hidden

    for paragraph in document.xpath("//w:body//w:p", namespaces=NS):
        check_background(paragraph.find("w:pPr", NS))
        for cell in paragraph.xpath("ancestor::w:tc", namespaces=NS):
            check_background(cell.find("w:tcPr", NS))
        for row in paragraph.xpath("ancestor::w:tr", namespaces=NS):
            check_background(row.find("w:tblPrEx", NS))
            check_background(row.find("w:trPr", NS))
            row_hidden = row.find("w:trPr/w:hidden", NS)
            if row_hidden is not None and enabled(row_hidden):
                return True
        pstyle = paragraph.find("w:pPr/w:pStyle", NS)
        table_hidden = default_hidden
        tables = paragraph.xpath("ancestor::w:tbl", namespaces=NS)
        if tables:
            check_background(tables[-1].find("w:tblPr", NS))
            table_style = tables[-1].find("w:tblPr/w:tblStyle", NS)
            table_hidden = apply_style(
                default_hidden,
                table_style.get(val) if table_style is not None else defaults.get("table"),
            )
        inherited = apply_style(
            table_hidden, pstyle.get(val) if pstyle is not None else defaults.get("paragraph")
        )
        for props in paragraph.xpath(".//m:ctrlPr/w:rPr", namespaces=NS):
            check_background(props)
            rstyle = props.find("w:rStyle", NS)
            control_hidden = apply_style(
                inherited, rstyle.get(val) if rstyle is not None else defaults.get("character")
            )
            direct = props.find("w:vanish", NS)
            if direct is not None:
                control_hidden = enabled(direct)
            if control_hidden:
                return True
        for run in paragraph.xpath(".//w:r | .//m:r", namespaces=NS):
            check_background(run.find("w:rPr", NS))
            rstyle = run.find("w:rPr/w:rStyle", NS)
            hidden = apply_style(
                inherited, rstyle.get(val) if rstyle is not None else defaults.get("character")
            )
            direct = run.find("w:rPr/w:vanish", NS)
            if direct is not None:
                hidden = enabled(direct)
            payload = "".join(
                run.xpath("./w:t/text() | ./m:t/text()", namespaces=NS)
            ) or run.xpath(
                "./w:tab | ./w:br | ./w:cr | ./w:drawing | ./w:sym | ./w:pict", namespaces=NS
            )
            if hidden and payload:
                return True
    return False


def _numbered_content(document: Any, styles: Any, numbering: Any) -> bool:
    """Reject generated numbering from direct properties and applicable style chains."""
    val = f"{{{NS['w']}}}val"
    style_map = {s.get(f"{{{NS['w']}}}styleId"): s for s in styles.findall("w:style", NS)}
    defaults = {
        s.get(f"{{{NS['w']}}}type"): sid
        for sid, s in style_map.items()
        if s.get(f"{{{NS['w']}}}default") in {"1", "true", "on"}
    }
    used_abstracts = {n.get(val) for n in numbering.findall("w:num/w:abstractNumId", NS)}
    associated_styles = set()
    for abstract in numbering.findall("w:abstractNum", NS):
        if abstract.get(f"{{{NS['w']}}}abstractNumId") in used_abstracts:
            associated_styles.update(
                abstract.xpath(".//w:pStyle/@w:val | w:styleLink/@w:val", namespaces=NS)
            )

    def chain(sid: str | None) -> list[Any]:
        result = []
        seen = set()
        while sid in style_map:
            if sid in seen:
                raise ValueError("UNSUPPORTED_NUMBERING")
            seen.add(sid)
            style = style_map[sid]
            result.append(style)
            parent = style.find("w:basedOn", NS)
            sid = parent.get(val) if parent is not None else None
        return result

    def numbered(paragraph: Any) -> bool:
        pstyle = paragraph.find("w:pPr/w:pStyle", NS)
        styles_used = chain(pstyle.get(val) if pstyle is not None else defaults.get("paragraph"))
        properties = [paragraph.find("w:pPr/w:numPr", NS)]
        properties.extend(s.find("w:pPr/w:numPr", NS) for s in styles_used)
        table_properties = []
        conditional = False
        tables = paragraph.xpath("ancestor::w:tbl", namespaces=NS)
        if tables:
            table_style = tables[-1].find("w:tblPr/w:tblStyle", NS)
            for style in chain(
                table_style.get(val) if table_style is not None else defaults.get("table")
            ):
                conditional |= bool(style.findall(".//w:tblStylePr/w:pPr/w:numPr", NS))
                table_properties.append(style.find("w:pPr/w:numPr", NS))
        unresolved = False
        for group in [
            properties,
            table_properties,
            [styles.find("w:docDefaults/w:pPrDefault/w:pPr/w:numPr", NS)],
        ]:
            if group is table_properties and conditional:
                return True
            for prop in group:
                if prop is None:
                    continue
                unresolved = True
                number = prop.find("w:numId", NS)
                if number is not None:
                    try:
                        return int(number.get(val, "")) != 0
                    except ValueError:
                        return True
        return unresolved or any(
            s.get(f"{{{NS['w']}}}styleId") in associated_styles for s in styles_used
        )

    return any(numbered(p) for p in document.xpath(".//w:p", namespaces=NS))


def _check_picture_containers(root: Any, image_sizes: dict[str, tuple[int, int]]) -> None:
    """Accept complete inline rectangular pictures, not hashes in orphan blips."""

    def one(node: Any, path: str) -> Any:
        found = node.findall(path, NS)
        if len(found) != 1:
            raise ValueError("INVALID_DRAWING_CONTAINER")
        return found[0]

    def integer(node: Any, attr: str, positive: bool = False) -> int:
        try:
            value = int(node.get(attr, ""))
        except ValueError as exc:
            raise ValueError("INVALID_DRAWING_CONTAINER") from exc
        if value < (1 if positive else 0) or value > 2**63 - 1:
            raise ValueError("INVALID_DRAWING_CONTAINER")
        return value

    def elements(node: Any) -> list[Any]:
        return [child for child in node if isinstance(child.tag, str)]

    regions = _body_regions(root)
    max_width = min(region[0] for region in regions) * 635
    max_height = min(region[1] for region in regions) * 635
    seen = set()
    drawing_ids: set[int] = set()
    for drawing in root.xpath("//w:body//w:drawing", namespaces=NS):
        blips = drawing.xpath(".//a:blip", namespaces=NS)
        if not blips:
            continue  # Non-image drawings are rejected by the unsupported-body check.
        if drawing.getparent().tag != f"{{{NS['w']}}}r":
            raise ValueError("INVALID_DRAWING_CONTAINER")
        children = elements(drawing)
        if len(children) != 1 or children[0].tag != f"{{{NS['wp']}}}inline":
            raise ValueError("INVALID_DRAWING_CONTAINER")
        inline = children[0]
        extent = one(inline, "wp:extent")
        size = (integer(extent, "cx", True), integer(extent, "cy", True))
        docpr = one(inline, "wp:docPr")
        drawing_id = integer(docpr, "id")
        if drawing_id in drawing_ids or docpr.get("name") is None:
            raise ValueError("INVALID_DRAWING_CONTAINER")
        drawing_ids.add(drawing_id)
        if docpr.get("hidden", "0") not in {"0", "false"}:
            raise ValueError("HIDDEN_CONTENT")
        graphic = one(inline, "a:graphic")
        data = one(graphic, "a:graphicData")
        if data.get("uri") != NS["pic"] or len(elements(data)) != 1:
            raise ValueError("INVALID_DRAWING_CONTAINER")
        picture = one(data, "pic:pic")
        properties = one(picture, "pic:nvPicPr/pic:cNvPr")
        if properties.get("hidden", "0") not in {"0", "false"}:
            raise ValueError("HIDDEN_CONTENT")
        one(picture, "pic:nvPicPr/pic:cNvPicPr")
        fill = one(picture, "pic:blipFill")
        blip = one(fill, "a:blip")
        if len(blips) != 1 or blips[0] != blip:
            raise ValueError("INVALID_DRAWING_CONTAINER")
        if blip.get(f"{{{NS['r']}}}link") is not None:
            raise ValueError("UNSUPPORTED_LINKED_IMAGE")
        pixels = image_sizes.get(blip.get(f"{{{NS['r']}}}embed", ""))
        if size[0] > max_width or size[1] > max_height:
            raise ValueError("IMAGE_DISPLAY_SCALE_INVALID")
        if pixels is None or min(size) < 12700 or abs(
            size[0] * pixels[1] - size[1] * pixels[0]
        ) > 0.02 * max(size[0] * pixels[1], size[1] * pixels[0]):
            raise ValueError("IMAGE_DISPLAY_SCALE_INVALID")
        seen.add(blip)
        stretch = one(fill, "a:stretch/a:fillRect")
        crops = [*fill.findall("a:srcRect", NS), stretch]
        if any(value != "0" for crop in crops for value in crop.attrib.values()):
            raise ValueError("UNSUPPORTED_IMAGE_RENDERING")
        shape = one(picture, "pic:spPr")
        transform = one(shape, "a:xfrm")
        if transform.get("rot", "0") != "0" or any(
            transform.get(key, "0") not in {"0", "false"} for key in ["flipH", "flipV"]
        ):
            raise ValueError("UNSUPPORTED_IMAGE_RENDERING")
        offset, shape_size = one(transform, "a:off"), one(transform, "a:ext")
        if (integer(offset, "x"), integer(offset, "y")) != (0, 0) or (
            integer(shape_size, "cx", True),
            integer(shape_size, "cy", True),
        ) != size:
            raise ValueError("INVALID_DRAWING_CONTAINER")
        if one(shape, "a:prstGeom").get("prst") != "rect":
            raise ValueError("UNSUPPORTED_IMAGE_RENDERING")
        for child in elements(shape):
            if child.tag in {f"{{{NS['a']}}}xfrm", f"{{{NS['a']}}}prstGeom"}:
                continue
            if child.tag == f"{{{NS['a']}}}effectLst" and not elements(child):
                continue
            if child.tag == f"{{{NS['a']}}}ln" and [n.tag for n in elements(child)] == [
                f"{{{NS['a']}}}noFill"
            ]:
                continue
            raise ValueError("UNSUPPORTED_IMAGE_RENDERING")
        # A common Office DPI annotation is harmless; image effects/alternate sources are not.
        for child in elements(blip):
            if child.tag != f"{{{NS['a']}}}extLst":
                raise ValueError("UNSUPPORTED_IMAGE_RENDERING")
            for extension in elements(child):
                annotations = elements(extension)
                if (
                    extension.tag != f"{{{NS['a']}}}ext"
                    or len(annotations) != 1
                    or annotations[0].tag
                    != "{http://schemas.microsoft.com/office/drawing/2010/main}useLocalDpi"
                    or annotations[0].get("val") not in {"0", "1", "false", "true"}
                    or elements(annotations[0])
                ):
                    raise ValueError("UNSUPPORTED_IMAGE_RENDERING")
    if any(blip not in seen for blip in root.xpath("//w:body//a:blip", namespaces=NS)):
        raise ValueError("INVALID_DRAWING_CONTAINER")


def _relationship_type_valid(value: str | None) -> bool:
    """Validate an absolute relationship-type URI without resolving or fetching it."""
    if (
        not value
        or any(c.isspace() or ord(c) < 32 for c in value)
        or re.search(r"%(?![0-9a-fA-F]{2})", value)
    ):
        return False
    try:
        uri = urlsplit(value)
    except ValueError:
        return False
    return bool(
        uri.scheme
        and (uri.netloc or uri.path)
        and (uri.scheme not in {"http", "https"} or uri.netloc)
    )


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
                if content_types.get(name) == CT.WML_COMMENTS:
                    comments = xml(archive.read(name))
                    if comments.tag != f"{{{NS['w']}}}comments":
                        raise ValueError("OPC_WORD_ROOT_INVALID")
                    if any(isinstance(child.tag, str) for child in comments) or (
                        comments.text and comments.text.strip()
                    ):
                        raise ValueError("UNSUPPORTED_COMMENTS")
                if name.endswith((".xml", ".rels")):
                    root = xml(archive.read(name))
                    if name.endswith(".rels"):
                        rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
                        if root.tag != f"{{{rel_ns}}}Relationships" or any(
                            r.tag != f"{{{rel_ns}}}Relationship"
                            for r in root
                            if isinstance(r.tag, str)
                        ):
                            raise ValueError("OPC_INVALID_DECLARATION")
                        relationship_ids: set[str] = set()
                        for relation in root:
                            if not isinstance(relation.tag, str):
                                continue
                            if not _relationship_type_valid(relation.get("Type")):
                                raise ValueError("OPC_RELATIONSHIP_TYPE_INVALID")
                            if not relation.get("Target"):
                                raise ValueError("OPC_RELATIONSHIP_TARGET_INVALID")
                            if relation.get("TargetMode", "Internal") not in {
                                "Internal",
                                "External",
                            }:
                                raise ValueError("OPC_RELATIONSHIP_MODE_INVALID")
                            rid = relation.get("Id", "")
                            if not rid or any(c in rid for c in "{}:"):
                                raise ValueError("OPC_RELATIONSHIP_ID_INVALID")
                            try:
                                etree.Element(rid)  # XML NCName syntax, including valid Unicode.
                            except ValueError as exc:
                                raise ValueError("OPC_RELATIONSHIP_ID_INVALID") from exc
                            if rid in relationship_ids:
                                raise ValueError("OPC_DUPLICATE_RELATIONSHIP_ID")
                            relationship_ids.add(rid)
                        base = posixpath.dirname(posixpath.dirname(name))
                        for rel in root:
                            if not isinstance(rel.tag, str):
                                continue
                            if rel.get("TargetMode") == "External":
                                raise ValueError("EXTERNAL_RELATIONSHIP")
                            target = _part_target(base, rel.get("Target", ""))
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
            image_sizes: dict[str, tuple[int, int]] = {}
            styles_target: str | None = None
            numbering_target: str | None = None
            settings_target: str | None = None
            font_targets: dict[str, str] = {}
            story_relationships: list[tuple[str, str, str]] = []
            rel_path = "word/_rels/document.xml.rels"
            if rel_path in names:
                for rel in xml(archive.read(rel_path)):
                    if not isinstance(rel.tag, str):
                        continue
                    target = _part_target("word", rel.get("Target", ""))
                    if rel.get("Type") == NS["r"] + "/image":
                        data = archive.read(target)
                        with Image.open(io.BytesIO(data)) as picture:
                            actual_type = Image.MIME.get(picture.format or "")
                            image_sizes[rel.get("Id", "")] = picture.size
                            picture.verify()
                        if actual_type is None or content_types.get(target) != actual_type:
                            raise ValueError("IMAGE_CONTENT_TYPE_INVALID")
                        relationships[rel.get("Id")] = hashlib.sha256(data).hexdigest()
                    kind = rel.get("Type", "").rsplit("/", 1)[-1]
                    if kind in {"theme", "fontTable"} and rel.get("Type") == NS["r"] + "/" + kind:
                        if kind in font_targets:
                            raise ValueError("OPC_INVALID_DECLARATION")
                        font_targets[kind] = target
                    if rel.get("Type") == NS["r"] + "/settings":
                        if settings_target is not None:
                            raise ValueError("OPC_INVALID_DECLARATION")
                        settings_target = target
                    if rel.get("Type") == NS["r"] + "/numbering":
                        if numbering_target is not None:
                            raise ValueError("OPC_INVALID_DECLARATION")
                        numbering_target = target
                    if rel.get("Type") == NS["r"] + "/styles":
                        if styles_target is not None:
                            raise ValueError("OPC_STYLE_RELATIONSHIP_INVALID")
                        styles_target = target
                    if kind in {"header", "footer", "footnotes", "endnotes"} and (
                        rel.get("Type") == NS["r"] + "/" + kind
                    ):
                        story_relationships.append((rel.get("Id", ""), kind, target))
            root = xml(archive.read("word/document.xml"))
            if _has_revisions(root):
                result["errors"].append("UNSUPPORTED_REVISIONS")
                return result
            if root.xpath(".//mc:AlternateContent", namespaces=NS):
                result["errors"].append("UNSUPPORTED_ALTERNATE_CONTENT")
                return result
            if any(
                rid not in relationships for rid in root.xpath("//a:blip/@r:embed", namespaces=NS)
            ):
                raise ValueError("INVALID_IMAGE_RELATIONSHIP")
            styles = (
                xml(archive.read(styles_target))
                if styles_target is not None
                else etree.Element(f"{{{NS['w']}}}styles")
            )
            numbering = (
                xml(archive.read(numbering_target))
                if numbering_target is not None
                else etree.Element(f"{{{NS['w']}}}numbering")
            )
            if styles.tag != f"{{{NS['w']}}}styles" or numbering.tag != f"{{{NS['w']}}}numbering":
                raise ValueError("OPC_WORD_ROOT_INVALID")
            if settings_target is not None:
                settings = xml(archive.read(settings_target))
                if settings.tag != f"{{{NS['w']}}}settings":
                    raise ValueError("OPC_WORD_ROOT_INVALID")
                if settings.xpath(".//mc:AlternateContent", namespaces=NS):
                    raise ValueError("UNSUPPORTED_ALTERNATE_CONTENT")
                if root.xpath("//w:body//w:r/w:tab", namespaces=NS):
                    for stop in settings.findall("w:defaultTabStop", NS):
                        raw = stop.get(f"{{{NS['w']}}}val", "")
                        bound = min(region[0] for region in _body_regions(root)) // 2
                        if not re.fullmatch(r"[0-9]+", raw) or not 1 <= int(raw) <= bound:
                            raise ValueError("UNSUPPORTED_TEXT_POSITION")
                if settings.find("w:writeProtection", NS) is not None:
                    raise ValueError("UNSUPPORTED_DOCUMENT_PROTECTION")
                for protection in settings.findall("w:documentProtection", NS):
                    if protection.get(f"{{{NS['w']}}}enforcement", "false") not in {
                        "0", "false", "off"
                    }:
                        raise ValueError("UNSUPPORTED_DOCUMENT_PROTECTION")
            if any(_has_revisions(part) for part in [styles, numbering]):
                result["errors"].append("UNSUPPORTED_REVISIONS")
                return result
            if any(
                part.xpath(".//mc:AlternateContent", namespaces=NS) for part in [styles, numbering]
            ):
                result["errors"].append("UNSUPPORTED_ALTERNATE_CONTENT")
                return result
            if root.xpath("//w:body//w:sdtPr/w:dataBinding", namespaces=NS):
                raise ValueError("UNSUPPORTED_DATA_BINDING")
            for lock in root.xpath("//w:body//w:sdtPr/w:lock", namespaces=NS):
                if lock.get(f"{{{NS['w']}}}val") not in {"unlocked", "sdtLocked"}:
                    raise ValueError("UNSUPPORTED_CONTENT_LOCK")
            if root.xpath("//w:body//w:bdo", namespaces=NS):
                raise ValueError("UNSUPPORTED_BIDI_OVERRIDE")
            _check_extension_wrappers(root)
            _check_payload_structure(root)
            _check_bookmarks(root)
            _check_picture_containers(root, image_sizes)
            if _numbered_content(root, styles, numbering):
                result["errors"].append("UNSUPPORTED_NUMBERING")
            font_table = (
                xml(archive.read(font_targets["fontTable"]))
                if "fontTable" in font_targets else etree.Element(f"{{{NS['w']}}}fonts")
            )
            theme = xml(archive.read(font_targets["theme"])) if "theme" in font_targets else None
            if font_table.tag != f"{{{NS['w']}}}fonts" or (
                theme is not None and theme.tag != f"{{{NS['a']}}}theme"
            ):
                raise ValueError("OPC_WORD_ROOT_INVALID")
            if any(
                part is not None and part.xpath(".//mc:AlternateContent", namespaces=NS)
                for part in (font_table, theme)
            ):
                raise ValueError("UNSUPPORTED_ALTERNATE_CONTENT")
            if _hidden_content(root, styles, font_table, theme):
                result["errors"].append("HIDDEN_CONTENT")
            story_types = {rid: kind for rid, kind, _ in story_relationships}
            for reference in root.xpath("//w:headerReference | //w:footerReference", namespaces=NS):
                kind = etree.QName(reference).localname.removesuffix("Reference")
                if story_types.get(reference.get(f"{{{NS['r']}}}id", "")) != kind:
                    raise ValueError("OPC_STORY_REFERENCE_INVALID")
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
                expected_root = {"header": "hdr", "footer": "ftr"}.get(kind, kind)
                if story.tag != f"{{{NS['w']}}}" + expected_root:
                    raise ValueError("OPC_STORY_ROOT_INVALID")
                if _has_revisions(story):
                    result["errors"].append("UNSUPPORTED_REVISIONS")
                    continue
                if story.xpath(".//mc:AlternateContent", namespaces=NS):
                    result["errors"].append("UNSUPPORTED_ALTERNATE_CONTENT")
                    continue
                text = word_text(story)
                visible = story.xpath(
                    "//m:oMath | //w:drawing | //a:blip | "
                    + " | ".join("//w:" + tag for tag in UNSUPPORTED_WORD_CONTENT),
                    namespaces=NS,
                )
                if text or visible or _numbered_content(story, styles, numbering):
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
            if root.xpath("//w:body//m:oMath[not(ancestor::w:p)]", namespaces=NS):
                raise ValueError("UNSUPPORTED_BLOCK_MATH")
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
                        "image_sizes": [
                            [
                                int(
                                    blip.xpath(
                                        "ancestor::wp:inline/wp:extent", namespaces=NS
                                    )[0].get(axis)
                                ) / 12700
                                for axis in ("cx", "cy")
                            ]
                            for blip in paragraph.xpath(".//a:blip", namespaces=NS)
                        ],
                        "markers": paragraph.xpath(".//w:bookmarkStart/@w:name", namespaces=NS),
                        "table": tables.index(parents[-1]) if parents else None,
                    }
                )
            for extent in root.xpath("//wp:extent", namespaces=NS):
                if int(extent.get("cx", "0")) <= 0 or int(extent.get("cy", "0")) <= 0:
                    raise ValueError("INVALID_IMAGE_EXTENT")
    except Image.DecompressionBombError:
        result["errors"].append("IMAGE_PIXEL_LIMIT")
    except (zipfile.BadZipFile, KeyError, etree.XMLSyntaxError, ValueError, OSError) as exc:
        known = {
            "DUPLICATE_ZIP_MEMBER",
            "PACKAGE_TOO_LARGE",
            "EXTERNAL_RELATIONSHIP",
            "MISSING_RELATIONSHIP_TARGET",
            "CORRUPT_MEDIA",
            "INVALID_IMAGE_EXTENT",
            "IMAGE_DISPLAY_SCALE_INVALID",
            "UNSUPPORTED_LINKED_IMAGE",
            "UNSUPPORTED_NESTED_TABLE",
            "UNSUPPORTED_BLOCK_MATH",
            "UNSUPPORTED_HORIZONTAL_MERGE",
            "INVALID_TABLE_GRID",
            "INVALID_BOOKMARK",
            "OPC_STORY_ROOT_INVALID",
            "OPC_STORY_REFERENCE_INVALID",
            "OPC_WORD_ROOT_INVALID",
            "UNSUPPORTED_COMMENTS",
            "UNSUPPORTED_DOCUMENT_PROTECTION",
            "UNSUPPORTED_CONTENT_LOCK",
            "UNSUPPORTED_MARKUP_COMPATIBILITY",
            "UNSUPPORTED_FONT_SCALE",
            "UNSUPPORTED_TEXT_POSITION",
            "UNSUPPORTED_DATA_BINDING",
            "INVALID_WORD_STRUCTURE",
            "UNSUPPORTED_ROW_HEIGHT",
            "UNSUPPORTED_TEXT_CASE",
            "UNSUPPORTED_LINE_HEIGHT",
            "UNSUPPORTED_FONT_MAPPING",
            "UNSUPPORTED_ALTERNATE_CONTENT",
            "UNSUPPORTED_TABLE_WIDTH",
            "UNSUPPORTED_BIDI_OVERRIDE",
            "UNSUPPORTED_OMML_VISIBILITY",
            "UNSUPPORTED_CELL_MARGINS",
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
            "OPC_RELATIONSHIP_ID_INVALID",
            "OPC_DUPLICATE_RELATIONSHIP_ID",
            "OPC_DUPLICATE_CONTENT_TYPE",
            "UNSUPPORTED_NUMBERING",
            "OPC_RELATIONSHIP_TYPE_INVALID",
            "OPC_RELATIONSHIP_TARGET_INVALID",
            "OPC_RELATIONSHIP_MODE_INVALID",
            "INVALID_DRAWING_CONTAINER",
            "UNSUPPORTED_IMAGE_RENDERING",
            "INVALID_OMML_NAMESPACE",
            "INVALID_OMML_STRUCTURE",
            "INVALID_WORD_TEXT",
            "HIDDEN_CONTENT",
        }
        code = str(exc) if str(exc) in known else type(exc).__name__.upper()
        result["errors"].append(code)
    return result
