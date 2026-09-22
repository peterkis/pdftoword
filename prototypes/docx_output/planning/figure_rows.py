"""Conservative single-row option layout from existing source figure bounds."""

from __future__ import annotations

import re
from itertools import pairwise

from ..common import Json


def plan_figure_rows(source: Json, output: Json) -> None:
    """Record one bounded decision per option group after final container widths exist."""
    blocks = {b["id"]: b for page in source["pages"] for b in page["blocks"]}
    assets = {a["id"]: a for a in source["assets"]}
    groups = {
        frozenset(bid for pair in group["pairs"] for bid in pair.values()): group
        for group in source["metadata"].get("figure_groups", [])
        if group["kind"] == "option_grid"
    }
    for section in output["sections"]:
        for node in section["nodes"]:
            if node["kind"] != "Group" or frozenset(node["source_ids"]) not in groups:
                continue
            group = groups[frozenset(node["source_ids"])]
            pairs = group["pairs"]
            count = len(pairs)
            decision: Json = {
                "columns": min(group.get("columns", 2), count),
                "basis": "existing_group" if "columns" in group else "estimated",
                "reason": "explicit_group_columns"
                if "columns" in group
                else "ambiguous_source_row",
                "figure_ids": [pair["figure"] for pair in pairs],
            }
            node["figure_layout"] = decision
            if "columns" in group or not 2 <= count <= 4:
                continue
            members = [blocks[bid] for bid in node["source_ids"]]
            if any(any("lock" in f for f in b["flags"]) for b in members):
                decision["reason"] = "locked_group"
                continue
            if any(
                not re.fullmatch(
                    r"[A-D][.．、]\s*", blocks[pair["label"]]["content"].get("plain_text", "")
                )
                for pair in pairs
            ):
                decision["reason"] = "unbounded_label_width"
                continue
            figures = [blocks[pair["figure"]] for pair in pairs]
            if any(
                f["geometry_source"] not in {"native_pdf", "pp_structure", "ovis_ocr2"}
                or f["content"]["kind"] != "image"
                or assets.get(f["content"].get("asset_id"), {}).get("source_bbox") != f["bbox"]
                for f in figures
            ):
                decision["reason"] = "unverified_figure_geometry"
                continue
            boxes = [f["bbox"] for f in figures]
            # Common vertical overlap, not a transitive chain; preserve input reading order.
            overlap = min(b[3] for b in boxes) - max(b[1] for b in boxes)
            if overlap < 0.5 * min(b[3] - b[1] for b in boxes) or any(
                left[2] > right[0] for left, right in pairwise(boxes)
            ):
                continue
            widths = section.get("column_widths_pt")
            available = widths[node.get("column_index", 0)] if widths else node["width_pt"]
            # Match the writer's cell inset; no figure shrink is used to make a row fit.
            cell_width = available / count - (30 if group.get("inline_labels") else 16)
            if any(b[2] - b[0] > cell_width for b in boxes):
                decision["reason"] = "insufficient_container_width"
                continue
            decision.update(columns=count, basis="source_based", reason="common_source_figure_row")
