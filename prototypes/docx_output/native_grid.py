"""Conservative ownership for complete, populated, axis-aligned native ruled grids.

This is a local image fallback witness, not editable table reconstruction. Path
bounding boxes alone never qualify: every horizontal must meet every vertical,
and every native run must fit exactly one populated cell. Ambiguity abstains.
"""

from __future__ import annotations

from itertools import pairwise

from .common import Json, intersection, union


def _strict_regions(
    objects: list[Json],
    chars: list[Json],
    *,
    allow_empty: bool = False,
    rejections: list[Json] | None = None,
) -> list[Json]:
    """Return auditable source membership without changing or discarding candidates."""
    paths = [o for o in objects if o["type"] == 2]
    components: list[list[Json]] = []
    for obj in paths:
        component = [obj]
        while True:
            touching = [
                c
                for c in components
                if any(intersection(a["bbox"], b["bbox"]) > 0 for a in component for b in c)
            ]
            if not touching:
                break
            for connected in touching:
                component.extend(connected)
                components.remove(connected)
        components.append(component)
    results = []
    for component in components:
        if any("solid_line" not in o for o in component):
            if rejections is not None:
                rejections.append(
                    {"bbox": union([o["bbox"] for o in component]), "reason": "UNKNOWN_PATH"}
                )
            continue
        horizontal, vertical = [], []
        for o in component:
            a, b = o["solid_line"]
            if abs(a[1] - b[1]) < 1e-5 and abs(a[0] - b[0]) > 1e-5:
                horizontal.append(o)
            elif abs(a[0] - b[0]) < 1e-5 and abs(a[1] - b[1]) > 1e-5:
                vertical.append(o)
        if len(horizontal) + len(vertical) != len(component):
            if rejections is not None:
                rejections.append(
                    {"bbox": union([o["bbox"] for o in component]), "reason": "NON_ORTHOGONAL_PATH"}
                )
            continue
        if min(len(horizontal), len(vertical)) < 3:
            if rejections is not None:
                rejections.append(
                    {"bbox": union([o["bbox"] for o in component]), "reason": "INCOMPLETE_GRID"}
                )
            continue
        # Stroke envelopes must physically connect at every lattice crossing.
        if any(intersection(h["bbox"], v["bbox"]) <= 0 for h in horizontal for v in vertical):
            if rejections is not None:
                rejections.append(
                    {"bbox": union([o["bbox"] for o in component]), "reason": "DISCONNECTED_GRID"}
                )
            continue
        xs = sorted(o["solid_line"][0][0] for o in vertical)
        ys = sorted(o["solid_line"][0][1] for o in horizontal)
        if len(set(xs)) != len(xs) or len(set(ys)) != len(ys):
            if rejections is not None:
                rejections.append(
                    {"bbox": union([o["bbox"] for o in component]), "reason": "DUPLICATE_GRID_AXIS"}
                )
            continue
        left = min(vertical, key=lambda o: o["solid_line"][0][0])["bbox"]
        right = max(vertical, key=lambda o: o["solid_line"][0][0])["bbox"]
        top = min(horizontal, key=lambda o: o["solid_line"][0][1])["bbox"]
        bottom = max(horizontal, key=lambda o: o["solid_line"][0][1])["bbox"]
        if any(
            not (
                left[0] <= min(p[0] for p in o["solid_line"]) <= left[2]
                and right[0] <= max(p[0] for p in o["solid_line"]) <= right[2]
            )
            for o in horizontal
        ):
            if rejections is not None:
                rejections.append(
                    {
                        "bbox": union([o["bbox"] for o in component]),
                        "reason": "HORIZONTAL_EDGE_EXTENDS",
                    }
                )
            continue
        if any(
            not (
                top[1] <= min(p[1] for p in o["solid_line"]) <= top[3]
                and bottom[1] <= max(p[1] for p in o["solid_line"]) <= bottom[3]
            )
            for o in vertical
        ):
            if rejections is not None:
                rejections.append(
                    {
                        "bbox": union([o["bbox"] for o in component]),
                        "reason": "VERTICAL_EDGE_EXTENDS",
                    }
                )
            continue
        bbox = union([o["bbox"] for o in component])
        ids = {o["id"] for o in component}
        # Unknown paths and images crossing the crop invalidate exclusive ownership.
        if any(
            o["type"] in (2, 3) and o["id"] not in ids and intersection(o["bbox"], bbox) > 0
            for o in objects
        ):
            if rejections is not None:
                rejections.append(
                    {"bbox": union([o["bbox"] for o in component]), "reason": "UNKNOWN_OVERLAP"}
                )
            continue
        cells = [
            {"bbox": [x0, y0, x1, y1], "native_run_ids": []}
            for y0, y1 in pairwise(ys)
            for x0, x1 in pairwise(xs)
        ]
        interior = [xs[0], ys[0], xs[-1], ys[-1]]
        members = [c for c in chars if intersection(c["bbox"], interior) > 0]
        valid = True
        for c in members:
            x0, y0, x1, y1 = c["bbox"]
            hits = [
                cell
                for cell in cells
                if cell["bbox"][0] <= x0 < x1 <= cell["bbox"][2]
                and cell["bbox"][1] <= y0 < y1 <= cell["bbox"][3]
            ]
            if len(hits) != 1:
                valid = False
                break
            hits[0]["native_run_ids"].append(c["source_id"])
        if not valid or (not allow_empty and any(not cell["native_run_ids"] for cell in cells)):
            if rejections is not None:
                rejections.append(
                    {
                        "bbox": union([o["bbox"] for o in component]),
                        "reason": "CELL_MEMBERSHIP_UNPROVEN",
                    }
                )
            continue
        results.append(
            {
                "basis": "complete_stroked_grid_populated_cells",
                "bbox": bbox,
                "path_ids": sorted(ids),
                "cells": cells,
                "native_run_ids": [c["source_id"] for c in members],
            }
        )
    return results


def _inside(inner: list[float], outer: list[float]) -> bool:
    return (
        outer[0] <= inner[0] < inner[2] <= outer[2] and outer[1] <= inner[1] < inner[3] <= outer[3]
    )


def ruled_regions(
    objects: list[Json],
    chars: list[Json],
    *,
    glyph_evidence: Json | None = None,
    rejections: list[Json] | None = None,
) -> list[Json]:
    """Keep the original strict witness, then try independently verified glyph cells."""
    results = _strict_regions(objects, chars)
    if glyph_evidence is None:
        return results
    bindings = glyph_evidence["runs"]
    tight = [{**c, "bbox": bindings.get(c["source_id"], {}).get("bbox", c["bbox"])} for c in chars]
    without_fills = [o for o in objects if "fill_rect" not in o]
    proposals = _strict_regions(without_fills, tight, allow_empty=True, rejections=rejections)
    for region in proposals:
        if any(region["bbox"] == old["bbox"] for old in results):
            continue
        reason = None
        members = region["native_run_ids"]
        if not members or any(bindings.get(rid, {}).get("status") != "VERIFIED" for rid in members):
            reason = "UNVERIFIED_CELL_GLYPHS"
        char_ids = [i for rid in members for i in bindings.get(rid, {}).get("char_indices", [])]
        interior = union([c["bbox"] for c in region["cells"]])
        observed = [
            g
            for g in glyph_evidence["glyphs"]
            if not g["generated"]
            and not g["text"].isspace()
            and (g["bbox"] is None or intersection(g["bbox"], interior) > 0)
        ]
        if (
            len(set(char_ids)) != len(char_ids)
            or set(char_ids) != {g["index"] for g in observed}
            or any(g["bbox"] is None or g["visibility"] != "painted" for g in observed)
        ):
            reason = "UNACCOUNTED_CELL_GLYPHS"
        fills = []
        for obj in objects:
            if "fill_rect" not in obj or intersection(obj["bbox"], region["bbox"]) <= 0:
                continue
            cells = [cell for cell in region["cells"] if _inside(obj["fill_rect"], cell["bbox"])]
            if len(cells) != 1:
                reason = "FILL_CROSSES_CELL"
                continue
            cell = cells[0]
            orders = [
                order
                for rid in cell["native_run_ids"]
                for order in bindings[rid].get("paint_orders", [])
            ]
            if cell["native_run_ids"] and (not orders or obj["paint_order"] >= min(orders)):
                reason = "FILL_NOT_BACKGROUND"
            fills.append(
                {
                    "path_id": obj["id"],
                    "cell_index": region["cells"].index(cell),
                    "rgba": obj["fill_rgba"],
                    "paint_order": obj["paint_order"],
                }
            )
        for fill in fills:
            cell = region["cells"][fill["cell_index"]]
            if not cell["native_run_ids"]:
                # A blank cell has no text to occlude. Require a matching same-row
                # fill whose painted text establishes the background convention.
                peers = [
                    f
                    for f in fills
                    if f["rgba"] == fill["rgba"]
                    and region["cells"][f["cell_index"]]["bbox"][1::2] == cell["bbox"][1::2]
                    and region["cells"][f["cell_index"]]["native_run_ids"]
                ]
                if not peers:
                    reason = "EMPTY_FILL_UNCONFIRMED"
        # Any unknown nontext drawing in this crop prevents exclusive ownership.
        allowed = set(region["path_ids"]) | {f["path_id"] for f in fills}
        if any(
            o["type"] != 1
            and o["id"] not in allowed
            and intersection(o["bbox"], region["bbox"]) > 0
            for o in objects
        ):
            reason = "UNKNOWN_GRID_OBJECT"
        if reason:
            if rejections is not None:
                rejections.append({"bbox": region["bbox"], "reason": reason})
            continue
        for cell in region["cells"]:
            cell["text_status"] = (
                "GLYPHS_VERIFIED" if cell["native_run_ids"] else "NO_VISIBLE_TEXT_OBSERVED"
            )
        region.update(
            basis="complete_stroked_grid_unique_glyph_cells",
            fill_paths=fills,
            path_ids=sorted(allowed),
            run_glyph_bindings={rid: bindings[rid] for rid in members},
        )
        results.append(region)
    return sorted(results, key=lambda r: (r["bbox"][1], r["bbox"][0]))
