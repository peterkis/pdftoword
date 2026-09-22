"""Local image ownership for connected rectangular classification diagrams.

Only explicit stroke rectangles and uniquely tipped horizontal links qualify.
This retains source pixels; it does not reconstruct editable drawing shapes.
"""

from __future__ import annotations

from itertools import pairwise

from .common import Json, intersection, union


def inside(inner: list[float], outer: list[float]) -> bool:
    """Require complete source enclosure without an invented geometric tolerance."""
    return (
        outer[0] <= inner[0] < inner[2] <= outer[2] and outer[1] <= inner[1] < inner[3] <= outer[3]
    )


def _side(point: list[float], frame: Json) -> bool:
    box, rect = frame["bbox"], frame["stroke_rect"]
    return bool(
        rect[1] < point[1] < rect[3]
        and (
            box[0] <= point[0] <= 2 * rect[0] - box[0] or 2 * rect[2] - box[2] <= point[0] <= box[2]
        )
    )


def _same_tip(a: list[float], b: list[float], line: Json, head: Json) -> bool:
    # Only the measured stroke radius explains source endpoint discrepancies.
    radius = min(line.get("stroke_width_pt", 0), head.get("stroke_width_pt", 0)) / 2
    return bool(max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= radius)


def diagram_regions(
    objects: list[Json],
    chars: list[Json],
    glyph_evidence: Json | None,
    rejections: list[Json] | None = None,
) -> list[Json]:
    """Return whole connected figures only when every drawing and glyph is accounted for."""
    if glyph_evidence is None:
        return []
    frames = [o for o in objects if "stroke_rect" in o]
    lines = [o for o in objects if "solid_line" in o]
    links = []
    for shaft in lines:
        if shaft.get("stroke_width_pt", 0) <= 0:
            continue
        a, b = shaft["solid_line"]
        if abs(a[1] - b[1]) > 1e-5 or a[0] == b[0]:
            continue
        ends = [[f for f in frames if _side(p, f)] for p in [a, b]]
        if any(len(e) != 1 for e in ends) or ends[0][0]["id"] == ends[1][0]["id"]:
            continue
        tips = []
        for head in lines:
            if head.get("stroke_width_pt", 0) <= 0:
                continue
            u, v = head["solid_line"]
            if abs(u[0] - v[0]) < 1e-5 or abs(u[1] - v[1]) < 1e-5:
                continue
            for tip_index, tip in enumerate([a, b]):
                for joint, wing in [(u, v), (v, u)]:
                    other = [a, b][1 - tip_index]
                    if _same_tip(tip, joint, shaft, head) and min(other[0], tip[0]) < wing[0] < max(
                        other[0], tip[0]
                    ):
                        tips.append((tip_index, head))
        if len(tips) != 1:
            continue
        tip_index, head = tips[0]
        links.append(
            {
                "from": ends[1 - tip_index][0]["id"],
                "to": ends[tip_index][0]["id"],
                "shaft_id": shaft["id"],
                "head_id": head["id"],
            }
        )
    groups: list[set[str]] = []
    for edge in links:
        member_set = {edge["from"], edge["to"]}
        touching = [g for g in groups if member_set & g]
        for g in touching:
            member_set |= g
            groups.remove(g)
        groups.append(member_set)
    by_id = {o["id"]: o for o in objects}
    bindings = glyph_evidence["runs"]
    results = []
    for group in groups:
        fs = [f for f in frames if f["id"] in group]
        edges = [e for e in links if e["from"] in group and e["to"] in group]
        ids = set(group) | {e[k] for e in edges for k in ["shaft_id", "head_id"]}
        bbox = union([by_id[i]["bbox"] for i in ids])
        reason = None
        if any(
            intersection(a["bbox"], b["bbox"]) > 0 for i, a in enumerate(fs) for b in fs[i + 1 :]
        ):
            reason = "OVERLAPPING_FRAMES"
        nodes = [{"frame_id": f["id"], "bbox": f["stroke_rect"], "native_run_ids": []} for f in fs]
        members = []
        for c in chars:
            witness = bindings.get(c["source_id"], {})
            box = witness.get("bbox", c["bbox"])
            if intersection(box, bbox) <= 0:
                continue
            hits = [node for node in nodes if inside(box, node["bbox"])]
            if witness.get("status") != "VERIFIED" or len(hits) != 1:
                reason = "UNOWNED_DIAGRAM_TEXT"
                continue
            hits[0]["native_run_ids"].append(c["source_id"])
            members.append(c["source_id"])
        if any(not node["native_run_ids"] for node in nodes):
            reason = "EMPTY_FRAME_UNPROVEN"
        chars_used = [i for rid in members for i in bindings[rid]["char_indices"]]
        visible = [
            g
            for g in glyph_evidence["glyphs"]
            if not g["generated"]
            and not g["text"].isspace()
            and (g["bbox"] is None or intersection(g["bbox"], bbox) > 0)
        ]
        if (
            len(chars_used) != len(set(chars_used))
            or set(chars_used) != {g["index"] for g in visible}
            or any(g["bbox"] is None or g["visibility"] != "painted" for g in visible)
        ):
            reason = "UNACCOUNTED_DIAGRAM_GLYPHS"
        decorations = []
        for obj in objects:
            if obj["id"] in ids or obj["type"] == 1 or intersection(obj["bbox"], bbox) <= 0:
                continue
            owners = [f for f in fs if inside(obj["bbox"], f["bbox"])]
            if len(owners) != 1:
                reason = "UNKNOWN_DIAGRAM_DRAWING"
                continue
            owner = owners[0]
            if "fill_rect" in obj:
                node = next(n for n in nodes if n["frame_id"] == owner["id"])
                orders = [
                    n for rid in node["native_run_ids"] for n in bindings[rid]["paint_orders"]
                ]
                if not orders or obj["paint_order"] >= min(orders):
                    reason = "FOREGROUND_FRAME_FILL"
                    continue
            elif "solid_line" in obj:
                a, b = obj["solid_line"]
                if abs(a[1] - b[1]) > 1e-5 or not (_side(a, owner) and _side(b, owner)):
                    reason = "UNKNOWN_FRAME_LINE"
                    continue
            else:
                reason = "UNKNOWN_DIAGRAM_DRAWING"
                continue
            decorations.append(obj["id"])
        ids.update(decorations)
        if reason:
            if rejections is not None:
                rejections.append({"bbox": bbox, "reason": reason})
            continue
        results.append(
            {
                "basis": "connected_frames_unique_directed_links_and_glyphs",
                "bbox": bbox,
                "path_ids": sorted(ids),
                "nodes": nodes,
                "edges": edges,
                "native_run_ids": members,
                "run_glyph_bindings": {rid: bindings[rid] for rid in members},
            }
        )
    return results


def attach_captions(ir: Json, page: Json) -> None:
    """Use adjacent explicit figure captions without treating their number as a question."""
    import re

    from .common import relation

    blocks = page["blocks"]
    for figure, caption in pairwise(blocks):
        if "native_diagram_image_fallback" not in figure["flags"]:
            continue
        text = caption["content"].get("plain_text", "")
        fb, cb = figure["bbox"], caption["bbox"]
        if (
            not re.match(r"^\s*图\s*[0-9０-９]+", text)
            or not 0 <= cb[1] - fb[3] < 35
            or not fb[0] <= (cb[0] + cb[2]) / 2 <= fb[2]
        ):
            continue
        caption["type"] = "caption"
        relation(
            ir,
            "caption_of",
            caption["id"],
            figure["id"],
            {"basis": "native_verified_diagram_adjacent_explicit_caption"},
        )
        ir["metadata"].setdefault("figure_groups", []).append(
            {
                "page_index": page["page_index"],
                "kind": "shared_row",
                "pairs": [{"figure": figure["id"], "label": caption["id"]}],
            }
        )
