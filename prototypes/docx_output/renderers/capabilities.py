"""Explicit supported POC subset; unsupported plans keep the existing writer."""

from __future__ import annotations

from ..common import Json
from ..planning.render_plan import LEGACY_LAYOUT, RenderPlan


def unsupported(plan: RenderPlan) -> list[Json]:
    """Never trade source styles, layout groups or known OMML for upstream defaults."""
    ir = plan.document
    findings = []
    if plan.output_layout != LEGACY_LAYOUT:
        findings.append({"code": "OUTPUT_LAYOUT_UNSUPPORTED"})
    if ir["styles"] or ir["metadata"].get("layout_profile") == "pp_geometry_flow":
        findings.append({"code": "SOURCE_STYLES_OR_GEOMETRY_LAYOUT_UNSUPPORTED"})
    for key in ("inline_parts", "figure_groups", "text_groups", "layout_by_page"):
        if ir["metadata"].get(key):
            findings.append({"code": "LEGACY_GROUPING_UNSUPPORTED", "field": key})
    for page in ir["pages"]:
        for b in page["blocks"]:
            if b["type"] not in {
                "paragraph",
                "major_question",
                "question",
                "subquestion",
                "option",
                "text_line",
                "text_span",
                "figure",
                "caption",
                "table",
                "formula",
                "footer",
                "page_number",
                "heading",
            }:
                findings.append(
                    {
                        "code": "BLOCK_TYPE_UNSUPPORTED",
                        "source_id": b["id"],
                        "block_type": b["type"],
                    }
                )
            if b["type"] == "figure" and b["content"]["kind"] != "image":
                findings.append({"code": "FIGURE_CONTENT_UNSUPPORTED", "source_id": b["id"]})
            if (
                b["type"] == "formula"
                and b["content"]["kind"] == "formula"
                and (
                    b["content"].get("render_mode") == "image"
                    or b["render_policy"] == "preserve_image"
                )
            ):
                findings.append({"code": "FORMULA_IMAGE_POLICY_UNSUPPORTED", "source_id": b["id"]})
            if (
                b["content"]["kind"] == "image"
                and b["content"].get("render_mode") != "preserve_as_image"
            ):
                findings.append({"code": "IMAGE_RENDER_MODE_UNSUPPORTED", "source_id": b["id"]})
            if b["content"]["kind"] == "formula" and b["type"] != "formula":
                findings.append(
                    {"code": "BLOCK_CONTENT_COMBINATION_UNSUPPORTED", "source_id": b["id"]}
                )
            if b["content"]["kind"] == "image" and b["content"].get("alt_text") is not None:
                findings.append({"code": "IMAGE_ALT_TEXT_UNSUPPORTED", "source_id": b["id"]})
            if b["type"] == "heading":
                findings.append({"code": "PLANNED_HEADING_LEVEL_UNSUPPORTED", "source_id": b["id"]})
            if b.get("style_ref") is not None:
                findings.append({"code": "BLOCK_SOURCE_STYLE_UNSUPPORTED", "source_id": b["id"]})
            if b["content"].get("runs"):
                findings.append({"code": "EXPLICIT_RUN_STYLES_UNSUPPORTED", "source_id": b["id"]})
    return findings
