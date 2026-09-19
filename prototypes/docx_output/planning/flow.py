"""Minimal evidence-aware flow plan; source coordinates remain read-only."""

from __future__ import annotations

import copy
import math
from collections import Counter
from dataclasses import dataclass

from jsonschema import Draft202012Validator

from ..common import ROOT, DemoError, Json, read, validate
from ..structure_processors.bridge import json_hash
from ..structure_processors.conservation import continuation_rejection
from ..structure_processors.docvortex import locked
from .render_plan import RenderPlan
from .styles import local_families, run_styles, styles


@dataclass
class FlowPlan(RenderPlan):
    """Typed v2 output nodes referencing preserved Layout IR 1.2 source blocks."""

    def as_dict(self) -> Json:
        """Serialize and validate the independent output contract."""
        result = {
            "schema_version": "render-plan/2",
            "document": copy.deepcopy(self.document),
            "output_layout": copy.deepcopy(self.output_layout),
        }
        Draft202012Validator(read(ROOT / "specs/render-plan.schema.json")).validate(result)
        validate(self.document)
        json_hash(result)  # Also rejects NaN/Infinity before any output file is created.
        expected = [bid for page in self.document["pages"] for bid in page["reading_order"]]
        actual = []
        for section in self.output_layout["sections"]:
            for node in section["nodes"]:
                leaves = node.get("children", [node])
                members = [bid for leaf in leaves for bid in leaf["source_ids"]]
                if node["kind"] == "Group" and Counter(members) != Counter(node["source_ids"]):
                    raise DemoError("FLOW_GROUP_SOURCE_COVERAGE_INVALID")
                actual.extend(members)
        if actual != expected or len(set(actual)) != len(actual):
            raise DemoError("FLOW_SOURCE_COVERAGE_INVALID")
        return result


def page_margins(page: Json) -> tuple[list[float], str]:
    """Infer from several trustworthy body boxes, otherwise use declared proportional margins."""
    width, height = page["width_pt"], page["height_pt"]
    boxes = [
        b["bbox"]
        for b in page["blocks"]
        if b["content"]["kind"] == "text"
        and b["geometry_source"] in {"native_pdf", "pp_structure"}
        and b["type"] in {"paragraph", "question", "text_line"}
        and 0 <= b["bbox"][0] < b["bbox"][2] <= width
    ]
    left = right = min(36.0, width * 0.06)
    if len(boxes) >= 3:
        left = min(width * 0.15, max(0, min(b[0] for b in boxes)))
        right = min(width * 0.15, max(0, width - max(b[2] for b in boxes)))
        basis = "measured_body_distribution"
    else:
        basis = "inferred_proportional_margin"
    vertical = min(36.0, height * 0.06)
    return [left, vertical, right, vertical], basis


def plan_flow(
    source: Json, profile: Json | None = None, *, families: set[str] | None = None
) -> FlowPlan:
    """Plan source-sized sections, stable styles and only source-validated shared joins."""
    validate(source)
    if source["schema_version"] not in {"layout-ir/1.1", "layout-ir/1.2"}:
        raise DemoError("FLOW_REQUIRES_IR_1_1_SOURCE")
    profile = copy.deepcopy(
        profile if profile is not None else source.get("planning", {}).get("profile_settings", {})
    )
    if set(profile) - {
        "body_size_pt",
        "latin_font",
        "east_asia_font",
        "margins_pt",
        "page_size_pt",
    }:
        raise DemoError("UNKNOWN_FLOW_PROFILE_FIELD")
    families = local_families() if families is None else families
    style_map, issues = styles(source, profile, families)
    document = copy.deepcopy(source)
    document["schema_version"] = "layout-ir/1.2"
    document["output_styles"] = style_map
    document["planning"] = {
        "profile": "flow-v1",
        "source_ir_sha256": json_hash(source),
        "source_schema_version": source["schema_version"],
        "profile_settings": profile,
    }
    output: Json = {"mode": "flow_v1", "sections": [], "issues": issues, "generated_join_spaces": 0}
    assets = {a["id"]: a for a in source["assets"]}
    shared = source["metadata"].get("docvortex_structure", {}).get("conservation")
    joins = (
        {
            (r["from"], r["to"])
            for r in source["relations"]
            if r["type"] == "continuation_of"
            and r.get("evidence", {}).get("basis") == "docvortex_public_postprocess"
        }
        if shared
        else set()
    )
    all_blocks = {b["id"]: b for p in source["pages"] for b in p["blocks"]}
    last_node: Json | None = None
    for page in source["pages"]:
        margins, basis = page_margins(page)
        margins = list(profile.get("margins_pt", margins))
        size = list(profile.get("page_size_pt", [page["width_pt"], page["height_pt"]]))
        if (
            len(size) != 2
            or len(margins) != 4
            or any(type(v) not in (int, float) for v in [*size, *margins])
            or not all(math.isfinite(v) for v in [*size, *margins])
            or min(size) <= 0
            or min(margins) < 0
            or size[0] <= margins[0] + margins[2]
            or size[1] <= margins[1] + margins[3]
        ):
            raise DemoError("INVALID_FLOW_PAGE_PROFILE")
        width = size[0] - margins[0] - margins[2]
        height = size[1] - margins[1] - margins[3]
        key = [size, margins]
        if not output["sections"] or output["sections"][-1]["geometry_key"] != key:
            section: Json = {
                "kind": "Section",
                "id": f"section-{len(output['sections'])}",
                "source_pages": [],
                "page_size_pt": size,
                "margins_pt": margins,
                "margin_basis": "explicit_profile" if "margins_pt" in profile else basis,
                "geometry_key": key,
                "nodes": [],
            }
            output["sections"].append(section)
            last_node = None
        else:
            section = output["sections"][-1]
        section["source_pages"].append(page["page_index"])
        grouped: set[str] = set()
        groups: list[Json] = []
        for category in ("text_groups", "figure_groups"):
            for group in source["metadata"].get(category, []):
                if group["page_index"] != page["page_index"]:
                    continue
                members = (
                    [bid for row in group["rows"] for bid in row]
                    if category == "text_groups"
                    else [bid for pair in group["pairs"] for bid in pair.values()]
                )
                positions = sorted(page["reading_order"].index(bid) for bid in members)
                if positions and positions != list(range(positions[0], positions[-1] + 1)):
                    raise DemoError("FLOW_NONCONTIGUOUS_GROUP")
                if grouped.intersection(members):
                    raise DemoError("FLOW_OVERLAPPING_GROUPS")
                grouped.update(members)
                groups.append(
                    {
                        "kind": "Group",
                        "id": f"group-{page['page_index']}-{len(groups)}",
                        "source_ids": members,
                        "children": [],
                        "width_pt": width,
                        "group_type": category,
                    }
                )
        by_id = {b["id"]: b for b in page["blocks"]}
        if len(by_id) != len(page["reading_order"]) or set(by_id) != set(page["reading_order"]):
            raise DemoError("FLOW_SOURCE_COVERAGE_INVALID")
        for bid in page["reading_order"]:
            block = by_id[bid]
            content = block["content"]
            role = (
                "heading"
                if block["type"] == "heading"
                else "caption"
                if block["type"] == "caption"
                else "footer"
                if block["type"] in {"footer", "page_number"}
                else "body"
            )
            style = style_map[role]
            alignment = source["styles"].get(block.get("style_ref"), {}).get("alignment", "left")
            if alignment not in {"left", "center", "right", "justify"}:
                alignment = "left"
            indent = 0.0
            if block["geometry_source"] in {"native_pdf", "pp_structure"} and bid not in grouped:
                indent = max(0.0, min(width * 0.25, block["bbox"][0] - margins[0]))
            node: Json = {
                "kind": "Table"
                if block["type"] == "table"
                else "Figure"
                if content["kind"] == "image"
                else "Paragraph",
                "id": "flow-" + bid,
                "source_ids": [bid],
                "style_id": role,
                "width_pt": width - indent,
                "alignment": alignment,
                "indent_pt": indent,
                "right_indent_pt": 0.0,
                "space_before_pt": style["space_before_pt"],
                "space_after_pt": style["space_after_pt"],
                "line_spacing": style["line_spacing"],
                "keep_with_next": block["type"] in {"heading", "caption", "question"},
                "widow_control": True,
                "runs": {
                    bid: run_styles(
                        block, style, families, east_asia_override="east_asia_font" in profile
                    )
                },
                "joiners": {},
                "height_limit_pt": max(
                    1.0, height - style_map["body"]["font_size_pt"] * 1.5 - style["space_after_pt"]
                ),
            }
            if content["kind"] == "image":
                asset = assets[content["asset_id"]]
                pixels = [asset.get("pixel_width"), asset.get("pixel_height")]
                if all(isinstance(v, (int, float)) and v > 0 for v in pixels):
                    ratio = pixels[0] / pixels[1]
                else:
                    box = asset["source_bbox"]
                    ratio = (box[2] - box[0]) / (box[3] - box[1])
                natural = max(1.0, asset["source_bbox"][2] - asset["source_bbox"][0])
                node["width_pt"] = min(node["width_pt"], natural, node["height_limit_pt"] * ratio)
            elif content["kind"] != "text":
                raise DemoError("FLOW_CONTENT_REQUIRES_EXISTING_RENDER_ADAPTER")
            previous_id = last_node["source_ids"][-1] if last_node else None
            merge = bool(
                last_node
                and node["kind"] == "Paragraph"
                and last_node["kind"] == "Paragraph"
                and bid not in grouped
                and (bid, previous_id) in joins
                and not locked(block)
                and block["type"] == "paragraph"
                and previous_id is not None
                and continuation_rejection(source, bid, previous_id) is None
                and not any(
                    x in source["metadata"].get("inline_parts", {}) for x in (bid, previous_id)
                )
            )
            if merge:
                assert last_node is not None
                last_node["source_ids"].append(bid)
                last_node["runs"].update(node["runs"])
                previous_text = all_blocks[previous_id]["content"]["plain_text"]
                current_text = content["plain_text"]
                separator = (
                    "" if (previous_text[-1:].isspace() or current_text[:1].isspace()) else " "
                )
                last_node["joiners"][bid] = separator
                output["generated_join_spaces"] += len(separator)
                continue
            group = next((g for g in groups if bid in g["source_ids"]), None)
            if group:
                if group not in section["nodes"]:
                    section["nodes"].append(group)
                group["children"].append(node)
                last_node = None
            else:
                section["nodes"].append(node)
                last_node = node
    keep_confirmed_captions(source, output)
    plan = FlowPlan(document, output)
    validate(document)
    plan.as_dict()
    return plan


def keep_confirmed_captions(source: Json, output: Json) -> None:
    """Keep explicit adjacent manual caption ranges with their figure; never infer ownership."""
    page_of = {b["id"]: p["page_index"] for p in source["pages"] for b in p["blocks"]}
    owners: dict[str, list[str]] = {}
    for edge in source["relations"]:
        if edge["type"] == "caption_of" and edge.get("evidence", {}).get("manual") is True:
            owners.setdefault(edge["to"], []).append(edge["from"])
    for owner, captions in owners.items():
        members = {owner, *captions}
        adopted = False
        for section in output["sections"]:
            nodes = section["nodes"]
            indices = [i for i, node in enumerate(nodes) if set(node["source_ids"]) & members]
            if not indices:
                continue
            selected = [nodes[i] for i in indices]
            if (
                indices != list(range(indices[0], indices[-1] + 1))
                or {bid for node in selected for bid in node["source_ids"]} != members
                or any(node["kind"] not in {"Figure", "Paragraph"} for node in selected)
                or len({page_of[bid] for node in selected for bid in node["source_ids"]}) != 1
            ):
                continue
            for node in selected[:-1]:
                node["keep_with_next"] = True
            selected[-1]["keep_with_next"] = False
            adopted = True
        if not adopted:
            output["issues"].append(
                {"code": "CONFIRMED_CAPTION_GROUP_NOT_CONTIGUOUS", "source_ids": sorted(members)}
            )
