"""Public DOCX renderer with local asset authentication and verified range mapping."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.text.paragraph import Paragraph
from lxml import etree

from ..common import DemoError, Json, digest, safe_path, save
from ..docvortex_runtime import call_worker, local_implementation_identity
from ..planning.render_plan import RenderPlan
from ..structure_processors.bridge import bridge, direct_middle, inline_text, table_text
from ..writer import fonts, inspect_package
from .capabilities import unsupported
from .legacy import LegacyRenderer
from .verification import preserve_image_geometry, verify_formula, verify_inline_order, verify_table


def bind_source_ranges(raw: Path, target: Path, ir: Json, entries: list[Json]) -> list[Json]:
    """Bind only bijective verified OOXML body ranges; never match by nearest text or bbox."""
    doc = Document(str(raw))
    body = doc.element.body
    elements = [e for e in body if e.tag in {qn("w:p"), qn("w:tbl")}]
    if len(elements) != len(entries):
        raise DemoError("DOCVORTEX_OUTPUT_RANGE_COUNT_MISMATCH")
    records = []
    ns = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    }
    for index, (element, entry) in enumerate(zip(elements, entries, strict=True)):
        b, source = entry["block"], entry["raw"]
        root = etree.fromstring(etree.tostring(element))
        text = "".join(
            n.text or "" if n.tag == qn("w:t") else "\t" if n.tag == qn("w:tab") else "\n"
            for n in root.iter()
            if n.tag in {qn("w:t"), qn("w:tab"), qn("w:br"), qn("w:cr")}
        )
        expected = inline_text(source["content"])
        inline_formulas = []
        if isinstance(source["content"], list):
            inline_formulas = [s for s in source["content"] if s.get("type") == "equation_inline"]
            if inline_formulas:
                verify_inline_order(root, source["content"])
                expected = "".join(
                    inline_text(s.get("content"))
                    for s in source["content"]
                    if s.get("type") != "equation_inline"
                )
                if len(root.xpath(".//m:oMath", namespaces=ns)) != len(inline_formulas):
                    raise DemoError("DOCVORTEX_INLINE_FORMULA_NOT_OMML")
                for math, span in zip(
                    root.xpath(".//m:oMath", namespaces=ns), inline_formulas, strict=True
                ):
                    verify_formula(math, inline_text(span.get("content")))
        if source["type"] == "table":
            verify_table(element, source["content"], doc)
            expected = table_text(source["content"])
        formula_image = False
        if source["type"] == "equation":
            maths = root.xpath(".//m:oMath", namespaces=ns)
            if maths:
                if len(maths) != 1 or text:
                    raise DemoError("DOCVORTEX_FORMULA_UNVERIFIED")
                verify_formula(maths[0], expected)
            else:
                formula_image = bool(
                    source.get("image_path") and root.xpath(".//a:blip", namespaces=ns)
                )
                if not formula_image or text:
                    raise DemoError("DOCVORTEX_FORMULA_NOT_OMML")
        elif text != expected:
            raise DemoError("DOCVORTEX_OUTPUT_CONTENT_CHANGED")
        images = []
        blips = root.xpath(".//a:blip", namespaces=ns)
        if source["type"] == "image" or formula_image:
            if len(blips) != 1:
                raise DemoError("DOCVORTEX_IMAGE_RANGE_MISMATCH")
            rid = blips[0].get(qn("r:embed"))
            image_bytes = doc.part.related_parts[rid].blob
            image_hash = hashlib.sha256(image_bytes).hexdigest()
            aid = b["content"]["source_asset_id"] if formula_image else b["content"]["asset_id"]
            asset = next(a for a in ir["assets"] if a["id"] == aid)
            if asset["path"] != source["image_path"]:
                raise DemoError("DOCVORTEX_SOURCE_ASSET_MISMATCH")
            if image_hash != asset["sha256"]:
                raise DemoError("DOCVORTEX_IMAGE_BYTES_CHANGED")
            preserve_image_geometry(element, image_bytes, asset["source_bbox"])
            images.append(
                {
                    "sha256": image_hash,
                    "bbox": asset["source_bbox"],
                    "fallback": b["type"] != "figure",
                }
            )
        elif blips:
            raise DemoError("DOCVORTEX_UNEXPECTED_IMAGE")
        marker = "p2w_" + hashlib.sha256(b["id"].encode()).hexdigest()[:32]
        start, end = OxmlElement("w:bookmarkStart"), OxmlElement("w:bookmarkEnd")
        start.set(qn("w:id"), str(index))
        start.set(qn("w:name"), marker)
        end.set(qn("w:id"), str(index))
        if element.tag == qn("w:p"):
            if b["type"] in {"caption", "footer"}:
                Paragraph(element, doc).style = "Caption"
            # pPr must remain first; markers surround the actual content runs.
            element.insert(1 if len(element) and element[0].tag == qn("w:pPr") else 0, start)
            element.append(end)
        else:
            body.insert(body.index(element), start)
            body.insert(body.index(element) + 1, end)
        records.append(
            {
                "marker": marker,
                "block_id": b["id"],
                "page": b["page_index"] + 1,
                "bbox": b["bbox"],
                "kind": b["type"],
                "images": images,
                "fallback": formula_image
                or (b["content"]["kind"] == "image" and b["type"] != "figure"),
                "formula_image": formula_image
                or (b["type"] == "formula" and b["content"]["kind"] == "image"),
            }
        )
    # Thin public-output adaptation to the existing explicit POC stylesheet.
    info = fonts()
    for section in doc.sections:
        section.page_width, section.page_height = Pt(595.28), Pt(841.89)
        section.top_margin = section.bottom_margin = Pt(40)
        section.left_margin = section.right_margin = Pt(45)
    for name, size in (("Normal", 11), ("Heading 1", 13), ("Heading 2", 13), ("Caption", 10)):
        style: Any = doc.styles[name]
        style.font.name = info["latin"] or "Arial"
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.element.get_or_add_rPr().get_or_add_rFonts().set(
            qn("w:eastAsia"), info["east_asia"] or "sans-serif"
        )
    doc.save(str(target))
    return records


class DocVortexRenderer:
    """Use public render_docx for supported plans, recording explicit Legacy fallback."""

    name = "docvortex-public"
    version = "0.4.9/p2w-1"

    def render(self, job: Path, plan: RenderPlan, revision: str) -> Json:
        """Never invoke a parser, provider, or deterministic structure stage here."""
        if revision not in {"auto", "reviewed"}:
            raise DemoError("INVALID_REVISION")
        target = safe_path(job, f"{revision}.docx")
        if target.exists() and revision == "auto":
            raise DemoError("AUTO_IMMUTABLE")
        findings = unsupported(plan)
        raw = job / f"docvortex.raw.{revision}.docx"
        audit: Json = {
            "public_call": "NOT_RUN",
            "fallback": False,
            "losses": findings,
            "local_implementation_sha256": local_implementation_identity(),
        }
        if not findings:
            try:
                value = bridge(plan.document, for_renderer=True)
                middle = direct_middle(value)
                save(job / f"docvortex.middle.{revision}.json", middle)
                save(job / f"source-ledger.{revision}.json", value.ledger)
                registry = {}
                for asset in plan.document["assets"]:
                    path = safe_path(job, asset["path"])
                    if not path.is_file() or digest(path) != asset["sha256"]:
                        raise DemoError("DOCVORTEX_ASSET_HASH_MISMATCH")
                    registry[asset["path"]] = asset["sha256"]
                # Retain previous raw candidate on reviewed re-export.
                import uuid

                raw = job / f"docvortex.raw.{revision}.{uuid.uuid4().hex}.docx"
                audit["public_call"] = "ATTEMPTED"
                audit["worker"] = call_worker(
                    {
                        "action": "render",
                        "job": str(job),
                        "middle": middle,
                        "assets": registry,
                        "output": str(raw),
                    }
                )
                audit["public_call"] = "COMPLETE"
                audit["raw_docx"] = raw.name
                pending = job / f"docvortex.pending.{uuid.uuid4().hex}.docx"
                records = bind_source_ranges(raw, pending, plan.document, value.ledger["entries"])
                stats = inspect_package(pending)
                pending.replace(target)
                save(
                    job / f"source-map.{revision}.json",
                    {
                        "schema_version": "docx-source-map/1.0",
                        "docx_sha256": digest(target),
                        "pages": [
                            {
                                "page": p["page_index"] + 1,
                                "width": p["width_pt"],
                                "height": p["height_pt"],
                            }
                            for p in plan.document["pages"]
                        ],
                        "blocks": records,
                        "relations": [
                            {k: r[k] for k in ("from", "to", "type")}
                            for r in plan.document["relations"]
                        ],
                    },
                )
                audit["losses"].extend(
                    {"code": "FORMULA_IMAGE_FALLBACK", "source_id": b["block_id"]}
                    for b in records
                    if b["formula_image"]
                )
                save(job / f"docvortex-render-audit.{revision}.json", audit)
                return {
                    **stats,
                    "effective_renderer": self.name,
                    "fonts": fonts(),
                    "rendered_fallback_asset_ids": [
                        e["block"]["content"][
                            "asset_id"
                            if e["block"]["content"]["kind"] == "image"
                            else "source_asset_id"
                        ]
                        for e, r in zip(value.ledger["entries"], records, strict=True)
                        if r["formula_image"]
                    ],
                    "editable_text_char_count": stats["package_text_char_count"],
                    "placed_figure_count": sum(b["kind"] == "figure" for b in records),
                    "formula_image_count": sum(b["formula_image"] for b in records),
                    "fallback_region_count": sum(b["fallback"] for b in records),
                    "omml_formula_count": sum(
                        e["raw"]["type"] == "equation" and not r["formula_image"]
                        for e, r in zip(value.ledger["entries"], records, strict=True)
                    )
                    + sum(
                        sum(s.get("type") == "equation_inline" for s in e["raw"]["content"])
                        for e in value.ledger["entries"]
                        if isinstance(e["raw"]["content"], list)
                    ),
                }
            except DemoError as exc:
                findings.append({"code": str(exc)})
        audit["fallback"] = True
        save(job / f"docvortex-render-audit.{revision}.json", audit)
        # Integrity failures must never downgrade into a writer that trusts changed bytes.
        for asset in plan.document["assets"]:
            source = safe_path(job, asset["path"])
            if not source.is_file() or digest(source) != asset["sha256"]:
                raise DemoError("DOCVORTEX_ASSET_HASH_MISMATCH")
        stats = LegacyRenderer().render(job, plan, revision)
        return {**stats, "effective_renderer": "legacy", "renderer_fallback": findings}
