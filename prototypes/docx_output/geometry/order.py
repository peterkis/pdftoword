"""Column-major order from independent measured support, never provider array indices."""

from __future__ import annotations

from itertools import pairwise

from ..common import DemoError, Json, union
from ..structure_processors.bridge import json_hash
from .binding import identity_bindings, validate_transition
from .candidate import rectangle


def column_order(page: Json, supports: Json) -> Json:
    """Return a replayable column proof, or a reason to retain the input order."""
    original = list(page["reading_order"])
    report: Json = {
        "schema_version": "column-order/1",
        "status": "ABSTAIN",
        "source_page_sha256": json_hash(page),
        "order": original,
        "supports": supports,
        "edges": [],
        "method": "measured_column_major",
    }
    try:
        by_id = {b["id"]: b for b in page["blocks"]}
        if len(by_id) != len(original) or set(by_id) != set(original):
            raise DemoError("ORDER_SOURCE_COVERAGE")
        boxes = {}
        wide = []
        for bid, block in by_id.items():
            support = supports.get(bid, {})
            if support.get("source_content_sha256") != json_hash(block["content"]):
                raise DemoError("ORDER_SUPPORT_MISSING_OR_STALE")
            if any(f.get("shared_line") for f in support.get("line_fragments", [])):
                raise DemoError("SHARED_LINE_ORDER_UNPROVEN")
            box = rectangle(support["bbox_pt"])
            if not (
                0 <= box[0] < box[2] <= page["width_pt"]
                and 0 <= box[1] < box[3] <= page["height_pt"]
            ):
                raise DemoError("ORDER_SUPPORT_OUT_OF_PAGE")
            boxes[bid] = box
            if box[2] - box[0] >= page["width_pt"] * 0.7:
                if block["type"] not in {"heading", "header", "footer", "page_number", "figure"}:
                    raise DemoError("WIDE_BODY_SCOPE_UNPROVEN")
                wide.append(bid)
        groups: list[list[str]] = []
        for bid in sorted(set(by_id) - set(wide), key=lambda key: boxes[key][0]):
            if groups and boxes[bid][0] < max(boxes[key][2] for key in groups[-1]):
                groups[-1].append(bid)
            else:
                groups.append([bid])
        if not 2 <= len(groups) <= 4 or any(len(group) < 2 for group in groups):
            raise DemoError("COLUMN_EVIDENCE_INSUFFICIENT")
        bounds = [union([boxes[bid] for bid in group]) for group in groups]
        for left_bound, right_bound in pairwise(bounds):
            if (
                right_bound[0] - left_bound[2] < page["width_pt"] * 0.02
                or min(left_bound[3], right_bound[3]) - max(left_bound[1], right_bound[1])
                < min(left_bound[3] - left_bound[1], right_bound[3] - right_bound[1]) * 0.5
            ):
                raise DemoError("COLUMN_GUTTER_OR_OVERLAP_UNPROVEN")
        members = {}
        ordered = []
        for col, group in enumerate(groups):
            group.sort(key=lambda bid: boxes[bid][1])
            for a, b in pairwise(group):
                if boxes[a][3] > boxes[b][1]:
                    raise DemoError("WITHIN_COLUMN_ORDER_AMBIGUOUS")
            ordered.extend(group)
            members.update(dict.fromkeys(group, col))
        top = min(box[1] for box in bounds)
        bottom = max(box[3] for box in bounds)
        preceding, following = [], []
        for bid in wide:
            if boxes[bid][3] <= top:
                preceding.append(bid)
            elif boxes[bid][1] >= bottom:
                following.append(bid)
            else:
                raise DemoError("SPANNING_MIDDLE_REQUIRES_BANDS")
        for ids in (preceding, following):
            ids.sort(key=lambda bid: boxes[bid][1])
            if any(boxes[a][3] > boxes[b][1] for a, b in pairwise(ids)):
                raise DemoError("SPANNING_ORDER_AMBIGUOUS")
        ordered = preceding + ordered + following
        edges = [list(pair) for pair in pairwise(ordered)]
        projected = {**page, "reading_order": ordered}
        content = validate_transition(page, projected, identity_bindings(page), edges)
        report.update(
            status="PROVEN",
            order=ordered,
            edges=edges,
            columns=bounds,
            membership=members,
            spanning_before=preceding,
            spanning_after=following,
            atomic_coverage=content["atomic_coverage"],
        )
    except (DemoError, ValueError, KeyError) as exc:
        report["reason"] = str(exc) if isinstance(exc, DemoError) else "INVALID_ORDER_SUPPORT"
    report["proof_sha256"] = json_hash(report)
    return report


def verify_order(original: Json, projected: Json, proof: Json) -> Json:
    """Recompute from sealed supports; a caller-supplied edge chain alone grants nothing."""
    expected = column_order(original, proof.get("supports", {}))
    if (
        expected != proof
        or expected["status"] != "PROVEN"
        or projected["reading_order"] != expected["order"]
    ):
        raise DemoError("ORDER_PROOF_INVALID")
    return expected
