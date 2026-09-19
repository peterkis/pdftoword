"""Read-only before/after artifact audit; never grants visual or platform acceptance."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from docx.oxml.ns import qn

from .common import DemoError, Json, digest, read
from .structure_processors.bridge import json_hash


def package_inventory(job: Path, revision: str = "auto") -> Json:
    """Reopen actual DOCX and prove every source marker encloses real payload."""
    path = job / f"{revision}.docx"
    document = Document(str(path))
    body = document.element.body
    records = read(job / f"source-map.{revision}.json")["blocks"]
    ir = read(job / f"layout.{revision}.json")
    blocks = {b["id"]: b for page in ir["pages"] for b in page["blocks"]}
    assets = {a["id"]: a for a in ir["assets"]}
    if Counter(r["block_id"] for r in records) != Counter(blocks.keys()):
        raise DemoError("SOURCE_RANGE_COVERAGE_MISMATCH")
    starts = body.xpath(".//w:bookmarkStart")
    ends = body.xpath(".//w:bookmarkEnd")
    spans = []
    for record in records:
        found = [s for s in starts if s.get(qn("w:name")) == record["marker"]]
        if len(found) != 1:
            raise DemoError("SOURCE_MARKER_NOT_UNIQUE")
        start = found[0]
        matches = [e for e in ends if e.get(qn("w:id")) == start.get(qn("w:id"))]
        if len(matches) != 1 or matches[0].getparent() is not start.getparent():
            raise DemoError("SOURCE_RANGE_UNRESOLVED")
        siblings = list(start.getparent())
        payload = siblings[siblings.index(start) + 1 : siblings.index(matches[0])]
        if not payload or not any(
            any(
                element.tag in {qn("w:t"), qn("w:drawing"), qn("m:oMath")}
                for element in node.iter()
            )
            for node in payload
        ):
            raise DemoError("SOURCE_RANGE_EMPTY")
        block = blocks[record["block_id"]]
        if record["bbox"] != block["bbox"] or record["page"] != block["page_index"] + 1:
            raise DemoError("SOURCE_RANGE_LOCATION_MISMATCH")
        parts = ir["metadata"].get("inline_parts", {}).get(block["id"])
        if parts is not None:
            if any("omml" in part for part in parts):
                raise DemoError("SOURCE_RANGE_MATH_AUDIT_NOT_SUPPORTED")
            expected_text = "".join(part.get("text", "") for part in parts)
            expected_images = [
                assets[part["asset_id"]]["sha256"] for part in parts if "asset_id" in part
            ]
        elif block["content"]["kind"] == "text":
            expected_text = block["content"]["plain_text"]
            expected_images = []
        elif block["content"]["kind"] == "image":
            expected_text = ""
            expected_images = [assets[block["content"]["asset_id"]]["sha256"]]
        else:
            raise DemoError("SOURCE_RANGE_CONTENT_AUDIT_NOT_SUPPORTED")
        elements = [element for node in payload for element in node.iter()]
        actual_text = "".join(
            (element.text or "")
            if element.tag == qn("w:t")
            else "\t"
            if element.tag == qn("w:tab")
            else "\n"
            for element in elements
            if element.tag in {qn("w:t"), qn("w:tab"), qn("w:br"), qn("w:cr")}
        )
        if actual_text != expected_text:
            raise DemoError("SOURCE_RANGE_TEXT_MISMATCH")
        actual_images = []
        for element in elements:
            if element.tag == qn("a:blip"):
                rid = element.get(qn("r:embed"))
                if rid not in document.part.related_parts:
                    raise DemoError("SOURCE_RANGE_IMAGE_RELATION_MISSING")
                actual_images.append(
                    hashlib.sha256(document.part.related_parts[rid].blob).hexdigest()
                )
        if actual_images != expected_images or actual_images != [
            im["sha256"] for im in record["images"]
        ]:
            raise DemoError("SOURCE_RANGE_IMAGE_MISMATCH")
        spans.append(record["block_id"])
    with ZipFile(path) as archive:
        media = Counter(
            hashlib.sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
            if name.startswith("word/media/")
        )
    return {
        "docx_sha256": digest(path),
        "source_ids": spans,
        "source_payloads_verified": True,
        "text_sha256": json_hash([t.text for t in body.xpath(".//w:t")]),
        "images": dict(media),
        "drawings": len(body.xpath(".//w:drawing")),
        "tables": len(body.xpath(".//w:tbl")),
        "omml": len(body.xpath(".//m:oMath")),
        "sections": len(document.sections),
        "source_map_sha256": digest(job / f"source-map.{revision}.json"),
    }


def audit_pair(before: Path, after: Path, revision: str = "auto") -> Json:
    """Keep unchanged-content checks separate from layout and human judgments."""
    original = read(before / f"layout.{revision}.json")
    candidate = read(after / f"layout.{revision}.json")
    left, right = package_inventory(before, revision), package_inventory(after, revision)

    def contents(ir: Json) -> Json:
        return {b["id"]: json_hash(b["content"]) for page in ir["pages"] for b in page["blocks"]}

    same_ir = contents(original) == contents(candidate)
    same_text = left["text_sha256"] == right["text_sha256"]
    same_images = left["images"] == right["images"] and left["drawings"] == right["drawings"]
    same_ranges = Counter(left["source_ids"]) == Counter(right["source_ids"])
    if not all((same_ir, same_text, same_images, same_ranges)):
        raise DemoError("BEFORE_AFTER_CONTENT_INVENTORY_MISMATCH")
    return {
        "schema_version": "reconstruction-acceptance/1",
        "before": left,
        "after": right,
        "content_inventory_unchanged": True,
        "images_unchanged": True,
        "source_ranges_nonempty": True,
        "relations_unchanged": original["relations"] == candidate["relations"],
        "reading_order_unchanged": [p["reading_order"] for p in original["pages"]]
        == [p["reading_order"] for p in candidate["pages"]],
        "visual_acceptance": "NOT_EVALUATED",
        "word_acceptance": "NOT_EVALUATED",
    }
