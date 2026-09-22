"""Evidence-only rectangular faces of ruled tables with partial internal borders."""

from __future__ import annotations

from itertools import pairwise

from .common import Json, intersection, union
from .native_diagram import inside


def _ink(obj: Json) -> list[float] | None:
    points = obj.get("solid_line", obj.get("white_line"))
    w = obj.get("stroke_width_pt", 0)
    if not points or w <= 0 or obj.get("line_cap") != 0:
        return None
    a, b = points
    r = w / 2
    if abs(a[1] - b[1]) < 1e-5:
        return [min(a[0], b[0]), a[1] - r, max(a[0], b[0]), a[1] + r]
    if abs(a[0] - b[0]) < 1e-5:
        return [a[0] - r, min(a[1], b[1]), a[0] + r, max(a[1], b[1])]
    return None


def _axes(values: list[float], eps: float) -> list[float]:
    result: list[float] = []
    for value in sorted(values):
        if not result or value - result[-1] > eps:
            result.append(value)
    return result


def _coverage(
    lo: float, hi: float, pos: float, horizontal: bool, paints: list[Json], eps: float
) -> str:
    intervals: list[tuple[float, float]] = []
    along, across = (0, 1) if horizontal else (1, 0)
    # Exact butt-cap stroke geometry, processed in original paint order.
    for obj in sorted(paints, key=lambda o: o["paint_order"]):
        box = _ink(obj)
        if box is None or not box[across] - eps <= pos <= box[across + 2] + eps:
            continue
        a, b = max(lo, box[along]), min(hi, box[along + 2])
        if b - a <= eps:
            continue
        if "white_line" in obj:
            intervals = [
                piece
                for x, y in intervals
                for piece in [(x, min(y, a)), (max(x, b), y)]
                if piece[1] - piece[0] > eps
            ]
        else:
            intervals.append((a, b))
            merged: list[tuple[float, float]] = []
            for x, y in sorted(intervals):
                if merged and x <= merged[-1][1] + eps:
                    merged[-1] = (merged[-1][0], max(y, merged[-1][1]))
                else:
                    merged.append((x, y))
            intervals = merged
    if not intervals:
        return "ABSENT"
    if len(intervals) == 1 and intervals[0][0] <= lo + eps and intervals[0][1] >= hi - eps:
        return "PRESENT"
    return "UNCERTAIN"


def merged_topology(objects: list[Json], rejections: list[Json]) -> list[Json]:
    """Merge only absent complete sides; reject open, partial and nonrectangular faces."""
    dark = [o for o in objects if "solid_line" in o and _ink(o) is not None]
    components: list[list[Json]] = []
    for obj in dark:
        group = [obj]
        while True:
            hits = [
                g
                for g in components
                if any(intersection(a["bbox"], b["bbox"]) > 0 for a in group for b in g)
            ]
            if not hits:
                break
            for g in hits:
                group.extend(g)
                components.remove(g)
        components.append(group)
    results = []
    for group in components:
        bbox = union([o["bbox"] for o in group])
        eps = max(1e-6, max(abs(v) for v in bbox) * 2**-22)
        hs = [o for o in group if abs(o["solid_line"][0][1] - o["solid_line"][1][1]) < 1e-5]
        vs = [o for o in group if o not in hs]
        xs = _axes([o["solid_line"][0][0] for o in vs], eps)
        ys = _axes([o["solid_line"][0][1] for o in hs], eps)
        if min(len(xs), len(ys)) < 3:
            continue
        whites = [o for o in objects if "white_line" in o and intersection(o["bbox"], bbox) > 0]
        paints = group + whites
        if any(_ink(o) is None for o in paints):
            continue
        radius = max(o["stroke_width_pt"] / 2 for o in group)
        bounds = [xs[0], ys[0], xs[-1], ys[-1]]
        if any(
            not (
                bounds[0] - radius - eps <= p[0] <= bounds[2] + radius + eps
                and bounds[1] - radius - eps <= p[1] <= bounds[3] + radius + eps
            )
            for o in group
            for p in o["solid_line"]
        ):
            rejections.append({"bbox": bbox, "reason": "DANGLING_TABLE_PATH"})
            continue
        nr, nc = len(ys) - 1, len(xs) - 1

        def junction(
            x: float,
            y: float,
            horizontal: bool,
            verticals: list[Json] = vs,
            horizontals: list[Json] = hs,
            precision: float = eps,
        ) -> float:
            perpendicular = verticals if horizontal else horizontals
            return float(
                max(
                    [
                        o["stroke_width_pt"] / 2
                        for o in perpendicular
                        if o["bbox"][0] - precision <= x <= o["bbox"][2] + precision
                        and o["bbox"][1] - precision <= y <= o["bbox"][3] + precision
                    ]
                    + [0.0]
                )
            )

        horizontal = []
        vertical = []
        edge_evidence = []
        for yi, y in enumerate(ys):
            row = []
            for xi, (a, b) in enumerate(pairwise(xs)):
                lo, hi = a + junction(a, y, True), b - junction(b, y, True)
                state = _coverage(lo, hi, y, True, paints, eps) if hi - lo > eps else "UNCERTAIN"
                row.append(state)
                edge_evidence.append(
                    {"axis": "h", "row": yi, "col": xi, "interval": [lo, hi], "state": state}
                )
            horizontal.append(row)
        for yi, (a, b) in enumerate(pairwise(ys)):
            row = []
            for xi, x in enumerate(xs):
                lo, hi = a + junction(x, a, False), b - junction(x, b, False)
                state = _coverage(lo, hi, x, False, paints, eps) if hi - lo > eps else "UNCERTAIN"
                row.append(state)
                edge_evidence.append(
                    {"axis": "v", "row": yi, "col": xi, "interval": [lo, hi], "state": state}
                )
            vertical.append(row)
        outer = [
            *horizontal[0],
            *horizontal[-1],
            *[row[0] for row in vertical],
            *[row[-1] for row in vertical],
        ]
        if any(s != "PRESENT" for s in outer) or any(
            e["state"] == "UNCERTAIN" for e in edge_evidence
        ):
            rejections.append(
                {"bbox": bbox, "reason": "INCOMPLETE_VISIBLE_BOUNDARY", "edges": edge_evidence}
            )
            continue
        parents = list(range(nr * nc))

        def find(i: int, parents: list[int] = parents) -> int:
            while parents[i] != i:
                i = parents[i]
            return i

        for rr in range(nr):
            for cc in range(nc):
                i = rr * nc + cc
                if cc + 1 < nc and vertical[rr][cc + 1] == "ABSENT":
                    parents[find(i)] = find(i + 1)
                if rr + 1 < nr and horizontal[rr + 1][cc] == "ABSENT":
                    parents[find(i)] = find(i + nc)
        groups: dict[int, list[tuple[int, int]]] = {}
        for i in range(nr * nc):
            groups.setdefault(find(i), []).append(divmod(i, nc))
        cells = []
        invalid = False
        for tiles in groups.values():
            r0, r1 = min(t[0] for t in tiles), max(t[0] for t in tiles) + 1
            c0, c1 = min(t[1] for t in tiles), max(t[1] for t in tiles) + 1
            if len(tiles) != (r1 - r0) * (c1 - c0):
                invalid = True
            if any(
                horizontal[rr][cc] != "ABSENT" for rr in range(r0 + 1, r1) for cc in range(c0, c1)
            ):
                invalid = True
            if any(
                vertical[rr][cc] != "ABSENT" for rr in range(r0, r1) for cc in range(c0 + 1, c1)
            ):
                invalid = True
            cells.append(
                {
                    "bbox": [xs[c0], ys[r0], xs[c1], ys[r1]],
                    "row": r0,
                    "col": c0,
                    "rowspan": r1 - r0,
                    "colspan": c1 - c0,
                    "native_run_ids": [],
                }
            )
        if invalid:
            rejections.append({"bbox": bbox, "reason": "NONRECTANGULAR_OR_INTERNAL_WALL"})
            continue
        results.append(
            {
                "basis": "paint_order_complete_intervals_rectangular_faces",
                "bbox": bbox,
                "path_ids": [o["id"] for o in paints],
                "cells": cells,
                "rows": nr,
                "columns": nc,
                "boundary_evidence": edge_evidence,
                "white_mask_path_ids": [o["id"] for o in whites],
            }
        )
    return results


def merged_regions(
    objects: list[Json], chars: list[Json], glyph_evidence: Json | None, rejections: list[Json]
) -> list[Json]:
    """Attach unique source glyphs and known non-occluding fills to proven faces."""
    if glyph_evidence is None:
        return []
    bindings = glyph_evidence["runs"]
    results = []
    for region in merged_topology(objects, rejections):
        # Complete unmerged grids stay on the existing N1/N3 path.
        if all(c["rowspan"] == c["colspan"] == 1 for c in region["cells"]):
            continue
        members = []
        reason = None
        for char in chars:
            witness = bindings.get(char["source_id"], {})
            box = witness.get("bbox", char["bbox"])
            if intersection(box, region["bbox"]) <= 0:
                continue
            hits = [c for c in region["cells"] if inside(box, c["bbox"])]
            if witness.get("status") != "VERIFIED" or len(hits) != 1:
                reason = "UNPROVEN_MERGED_CELL_GLYPHS"
                continue
            hits[0]["native_run_ids"].append(char["source_id"])
            members.append(char["source_id"])
        used = [i for rid in members for i in bindings[rid]["char_indices"]]
        glyphs = [
            g
            for g in glyph_evidence["glyphs"]
            if not g["generated"]
            and not g["text"].isspace()
            and (g["bbox"] is None or intersection(g["bbox"], region["bbox"]) > 0)
        ]
        if (
            not members
            or len(used) != len(set(used))
            or set(used) != {g["index"] for g in glyphs}
            or any(g["bbox"] is None or g["visibility"] != "painted" for g in glyphs)
        ):
            reason = "UNACCOUNTED_MERGED_CELL_GLYPHS"
        for mask in objects:
            if mask["id"] not in region["white_mask_path_ids"]:
                continue
            ink_box = _ink(mask)
            if ink_box is not None and any(
                g["bbox"] is not None
                and g["paint_order"] <= mask["paint_order"]
                and intersection(g["bbox"], ink_box) > 0
                for g in glyphs
            ):
                reason = "FOREGROUND_WHITE_MASK_GLYPH"
        fills = []
        for obj in objects:
            if (
                obj["id"] in region["path_ids"]
                or obj["type"] == 1
                or intersection(obj["bbox"], region["bbox"]) <= 0
            ):
                continue
            owners = [
                c
                for c in region["cells"]
                if "fill_rect" in obj and inside(obj["fill_rect"], c["bbox"])
            ]
            if len(owners) != 1:
                reason = "UNKNOWN_MERGED_TABLE_DRAWING"
                continue
            overlaps = [
                g
                for g in glyphs
                if g["bbox"] is not None and intersection(g["bbox"], obj["fill_rect"]) > 0
            ]
            if any(g["paint_order"] <= obj["paint_order"] for g in overlaps):
                reason = "FOREGROUND_MERGED_CELL_FILL"
                continue
            fills.append(
                {
                    "path_id": obj["id"],
                    "cell_index": region["cells"].index(owners[0]),
                    "paint_order": obj["paint_order"],
                    "rgba": obj["fill_rgba"],
                }
            )
        if reason:
            rejections.append({"bbox": region["bbox"], "reason": reason})
            continue
        for cell in region["cells"]:
            cell["text_status"] = (
                "GLYPHS_VERIFIED" if cell["native_run_ids"] else "NO_VISIBLE_TEXT_OBSERVED"
            )
        region.update(
            native_run_ids=members,
            fill_paths=fills,
            run_glyph_bindings={rid: bindings[rid] for rid in members},
            path_ids=[*region["path_ids"], *[f["path_id"] for f in fills]],
        )
        results.append(region)
    return results
