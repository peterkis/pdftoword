"""Lossless source ledger and normalized public Model/Middle JSON projection."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass

from ..common import DemoError, Json, validate

BRIDGE_VERSION = "p2w-docvortex-bridge/1"


def json_hash(value: object) -> str:
    """Hash canonical source data without logging it."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def normalized(box: list[float], page: Json) -> list[float]:
    """Convert PDF points to the upstream strict 0..1 bbox contract, without clipping."""
    result = [
        box[0] / page["width_pt"],
        box[1] / page["height_pt"],
        box[2] / page["width_pt"],
        box[3] / page["height_pt"],
    ]
    if not all(0 <= n <= 1 for n in result) or result[0] >= result[2] or result[1] >= result[3]:
        raise DemoError("BRIDGE_INVALID_GEOMETRY")
    return result


def inline_text(content: object) -> str:
    """Recover exact visible atoms from public text spans, never perform text cleanup."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(inline_text(x.get("content", "")) for x in content if isinstance(x, dict))
    return ""


@dataclass
class BridgeInput:
    """Separate immutable selected evidence from disposable upstream raw blocks."""

    model: Json
    ledger: Json
    source: Json


def bridge(selected: Json, *, for_renderer: bool = False) -> BridgeInput:
    """Translate selected IR only; never infer missing lines, confidence or producer identity."""
    validate(selected)
    seen: set[str] = set()
    entries = []
    pages = []
    page_map = []
    for page in selected["pages"]:
        ids = [b["id"] for b in page["blocks"]]
        if len(ids) != len(set(ids)) or seen.intersection(ids):
            raise DemoError("BRIDGE_DUPLICATE_SOURCE_ID")
        seen.update(ids)
        if len(page["reading_order"]) != len(ids) or set(page["reading_order"]) != set(ids):
            raise DemoError("BRIDGE_INCOMPLETE_READING_ORDER")
        by_id = {b["id"]: b for b in page["blocks"]}
        raw = []
        for index, bid in enumerate(page["reading_order"]):
            b = by_id[bid]
            content = b["content"]
            evidence = selected["metadata"].get("structure_evidence", {}).get(bid, {})
            item: Json = {"index": index, "bbox": normalized(b["bbox"], page)}
            kind = content["kind"]
            if kind == "image":
                assets = {a["id"]: a for a in selected["assets"]}
                aid = content["asset_id"]
                if aid not in assets:
                    raise DemoError("BRIDGE_ASSET_MISSING")
                item.update(type="image", content="", image_path=assets[aid]["path"])
            elif kind == "text":
                if for_renderer and b["type"] == "formula":
                    raise DemoError("FORMULA_STRUCTURE_EVIDENCE_MISSING")
                types = {
                    "heading": "paragraph_title",
                    "caption": "image_caption",
                    "footer": "footer",
                }
                item.update(
                    type=types.get(b["type"], "text"),
                    content=[{"type": "text", "content": content["plain_text"]}]
                    if content["plain_text"]
                    else [],
                )
                if (
                    for_renderer
                    and b["type"] == "table"
                    and not (
                        isinstance(evidence.get("selected_html"), str)
                        and evidence["selected_html"].strip()
                    )
                ):
                    raise DemoError("TABLE_STRUCTURE_EVIDENCE_MISSING")
                if b["type"] == "table" and evidence.get("selected_html"):
                    if for_renderer:
                        require_plain_table_markup(evidence["selected_html"])
                    if table_text(evidence["selected_html"]) != content["plain_text"]:
                        raise DemoError("TABLE_EVIDENCE_TEXT_MISMATCH")
                    item.update(type="table", content=evidence["selected_html"])
                if for_renderer and b["type"] in {"footer", "caption"}:
                    # Public default render skips auxiliary blocks; preserve source explicitly.
                    item["type"] = "text"
                if evidence.get("inline_spans"):
                    if for_renderer and any(
                        not isinstance(span, dict)
                        or set(span) != {"type", "content"}
                        or span["type"] not in {"text", "equation_inline"}
                        or not isinstance(span["content"], str)
                        for span in evidence["inline_spans"]
                    ):
                        raise DemoError("INLINE_SPAN_UNSUPPORTED")
                    if inline_text(evidence["inline_spans"]) != content["plain_text"]:
                        raise DemoError("INLINE_EVIDENCE_TEXT_MISMATCH")
                    item["content"] = copy.deepcopy(evidence["inline_spans"])
            elif kind == "formula" and content.get("latex"):
                item.update(type="equation", content=content["latex"])
                assets = {asset["id"]: asset for asset in selected["assets"]}
                aid = content["source_asset_id"]
                if aid not in assets:
                    raise DemoError("BRIDGE_FORMULA_ASSET_MISSING")
                if not for_renderer or content.get("render_mode") == "omml_with_image_fallback":
                    item["image_path"] = assets[aid]["path"]
            else:
                raise DemoError("BRIDGE_UNSUPPORTED_CONTENT")
            if evidence.get("coordinate_space") == "pdf_points" and evidence.get("lines"):
                item["lines"] = [
                    {**copy.deepcopy(line), "bbox": normalized(line["bbox"], page)}
                    for line in evidence["lines"]
                ]
            if evidence.get("_paragraph_boundary") is True:
                item["_paragraph_boundary"] = True
            if "angle" in evidence:
                item["angle"] = evidence["angle"]
            if b.get("engine_confidence") is not None:
                item["score"] = b["engine_confidence"]
            if "label" in evidence:
                item["label"] = evidence["label"]
            raw.append(item)
            entries.append(
                {
                    "source_id": bid,
                    "page_index": page["page_index"],
                    "raw_index": index,
                    "block": copy.deepcopy(b),
                    "evidence": copy.deepcopy(evidence),
                    "raw": copy.deepcopy(item),
                    "provenance": copy.deepcopy(selected["provenance"].get(bid, {})),
                }
            )
        pages.append(raw)
        page_map.append(page["page_index"])
    if page_map != sorted(set(page_map)):
        raise DemoError("BRIDGE_INVALID_PAGE_MAP")
    full = page_map == list(range(selected["source"]["page_count"]))
    model = {
        "schema": "docvortex.model",
        "schema_version": "2.0",
        "metadata": {
            "file_suffix": "pdf",
            "producer": {"name": "pdf2word", "version": BRIDGE_VERSION},
        },
        "extensions": {"pdf2word": {"input_ir_sha256": json_hash(selected)}},
        "page_index_map": [] if full else page_map,
        "pages": pages,
    }
    ledger = {
        "schema_version": "source-ledger/1",
        "input_ir_sha256": json_hash(selected),
        "entries": entries,
        "relations": copy.deepcopy(selected["relations"]),
        "source": copy.deepcopy(selected["source"]),
        "full_provenance": copy.deepcopy(selected["provenance"]),
        "metadata": copy.deepcopy(selected["metadata"]),
    }
    return BridgeInput(model, ledger, copy.deepcopy(selected))


def direct_middle(value: BridgeInput) -> Json:
    """Project finalized IR for rendering, without running structure postprocessing again."""
    pages = []
    for page, source_page in zip(value.model["pages"], value.source["pages"], strict=True):
        blocks = []
        for original in page:
            b = {
                k: copy.deepcopy(v)
                for k, v in original.items()
                if k not in {"lines", "angle", "score", "label"}
            }
            if b["type"] == "paragraph_title":
                # Public schema supports level >= 2; renderer capabilities reject Heading 1 plans.
                b["level"] = 2
            if b["type"] in {"image", "table"}:
                child = {**b, "type": b["type"] + "_body"}
                b = {"type": b["type"], "index": b["index"], "bbox": b["bbox"], "content": [child]}
            blocks.append(b)
        pages.append({"page_idx": source_page["page_index"], "blocks": blocks})
    return {
        "schema": "docvortex.middle",
        "schema_version": "2.0",
        "metadata": value.model["metadata"],
        "extensions": value.model["extensions"],
        "is_full_document": not value.model["page_index_map"],
        "pages": pages,
    }


def table_text(markup: str) -> str:
    """Read ordinary HTML text once, preserving explicit breaks and decoded entities."""
    from lxml import etree, html

    try:
        root = html.fragment_fromstring(
            markup, create_parent="div", parser=html.HTMLParser(no_network=True)
        )
    except (etree.ParserError, ValueError):
        raise DemoError("BRIDGE_TABLE_HTML_INVALID") from None

    def visible(node: etree._Element) -> str:
        if not isinstance(node.tag, str) or node.tag.lower() in {"script", "style"}:
            return ""
        result = node.text or ""
        for child in node:
            result += "\n" if child.tag == "br" else visible(child)
            result += child.tail or ""
        return result

    return visible(root)


def require_plain_table_markup(markup: str) -> None:
    """Limit the renderer POC to plain cells, spans and line breaks, preserving refusals."""
    from lxml import etree, html

    try:
        root = html.fragment_fromstring(
            markup, create_parent="div", parser=html.HTMLParser(no_network=True)
        )
    except (etree.ParserError, ValueError):
        raise DemoError("BRIDGE_TABLE_HTML_INVALID") from None
    if root.xpath(".//thead|.//th|.//tfoot"):
        raise DemoError("DOCVORTEX_TABLE_HEADER_UNSUPPORTED")
    if len(root.xpath(".//table")) != 1:
        raise DemoError("TABLE_MARKUP_UNSUPPORTED")
    for node in root.iterdescendants():
        allowed = {"rowspan", "colspan"} if node.tag == "td" else set()
        if node.tag not in {"table", "tbody", "tr", "td", "br"} or set(node.attrib) - allowed:
            raise DemoError("TABLE_RICH_CONTENT_UNSUPPORTED")
