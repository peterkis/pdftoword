"""Independent atomic coverage and relation-delta checks around shared processing."""

from __future__ import annotations

from ..common import DemoError, Json
from ..geometry.binding import identity_bindings, validate_transition
from .bridge import json_hash
from .docvortex import locked


def source_scopes(ir: Json) -> dict[str, tuple[int, str | None]]:
    """Keep existing question boundaries; do not infer new ownership from proximity."""
    result = {}
    question = None
    previous_page = None
    for page in ir["pages"]:
        if previous_page is not None and page["page_index"] != previous_page + 1:
            question = None
        blocks = {b["id"]: b for b in page["blocks"]}
        for bid in page["reading_order"]:
            block = blocks[bid]
            if block["type"] in {"major_question", "question", "subquestion"}:
                question = bid
            result[bid] = (page["page_index"], question)
        previous_page = page["page_index"]
    blocks = {b["id"]: b for page in ir["pages"] for b in page["blocks"]}
    parents: dict[str, list[str]] = {}
    for edge in ir["relations"]:
        if edge["type"] == "contains":
            parents.setdefault(edge["to"], []).append(edge["from"])
    for bid in result:
        frontier = list(parents.get(bid, []))
        seen = {bid}
        owners = set()
        while frontier:
            parent = frontier.pop()
            if parent in seen or parent not in blocks:
                owners.add("ambiguous:" + bid)
                continue
            seen.add(parent)
            if blocks[parent]["type"] in {"major_question", "question", "subquestion"}:
                owners.add(parent)
            else:
                frontier.extend(parents.get(parent, []))
        if owners:
            result[bid] = (
                result[bid][0],
                next(iter(owners)) if len(owners) == 1 else "ambiguous:" + bid,
            )
    return result


def continuation_rejection(ir: Json, origin: str, target: str) -> str | None:
    """Guard public continues_prev proposals against source boundaries before adoption."""
    scopes = source_scopes(ir)
    blocks = {b["id"]: b for p in ir["pages"] for b in p["blocks"]}
    if origin not in blocks or target not in blocks:
        return "RELATION_SOURCE_UNKNOWN"
    a, b = blocks[target], blocks[origin]
    if locked(a) or locked(b):
        return "RELATION_MANUAL_LOCK"
    if a["type"] != "paragraph" or b["type"] != "paragraph":
        return "RELATION_NON_PARAGRAPH"
    if scopes[origin][0] - scopes[target][0] not in {0, 1}:
        return "RELATION_NONCONSECUTIVE_PAGE"
    if any(
        scope[1] and scope[1].startswith("ambiguous:") for scope in (scopes[origin], scopes[target])
    ):
        return "RELATION_AMBIGUOUS_OWNERSHIP"
    if scopes[origin][1] != scopes[target][1]:
        return "RELATION_CROSS_QUESTION"
    order = [bid for p in ir["pages"] for bid in p["reading_order"]]
    if order.index(origin) != order.index(target) + 1:
        return "RELATION_NONADJACENT_SOURCE"
    selected_columns = {}
    for report in ir["metadata"].get("column_layout", {}).values():
        if report["status"] == "APPLIED":
            for band in report["bands"]:
                for col in band["columns"]:
                    selected_columns.update(dict.fromkeys(col["source_ids"], col["id"]))
    if (origin in selected_columns or target in selected_columns) and selected_columns.get(
        origin
    ) != selected_columns.get(target):
        return "RELATION_CROSS_SELECTED_COLUMN_OR_BAND"
    column = {}
    for p in ir["pages"]:
        support = ir.get("metadata", {}).get("geometry_support", {}).get(str(p["page_index"]), {})
        if support:
            from ..geometry.order import column_order

            proof = column_order(p, support)
            if proof["status"] == "PROVEN":
                column.update(proof["membership"])
    if origin in column and target in column and column[origin] != column[target]:
        return "RELATION_CROSS_COLUMN"
    # Independent line evidence is required by the adapter. Horizontal separation
    # cannot become continuation merely because the public stage proposed it.
    evidence = ir.get("metadata", {}).get("structure_evidence", {})
    left = evidence.get(target, {}).get("lines", [])
    right = evidence.get(origin, {}).get("lines", [])
    if left and right:
        x, y = left[-1]["bbox"], right[0]["bbox"]
        width = min(x[2] - x[0], y[2] - y[0])
        if width <= 0 or min(x[2], y[2]) - max(x[0], y[0]) < width * 0.5:
            return "RELATION_CROSS_COLUMN"
    return None


def stage_owned(relation: Json) -> bool:
    """Only untouched stage continuations may be retired or refreshed."""
    return (
        relation["type"] == "continuation_of"
        and relation.get("method") == "demo_rule"
        and relation.get("evidence", {}).get("basis") == "docvortex_public_postprocess"
        and not relation.get("evidence", {}).get("manual")
    )


def verify_shared(before: Json, after: Json) -> Json:
    """Check actual shared output, preserving every atomic source and external relation."""
    if [p["page_index"] for p in before["pages"]] != [p["page_index"] for p in after["pages"]]:
        raise DemoError("SHARED_PAGE_INVENTORY_CHANGED")
    coverage = []
    for a, b in zip(before["pages"], after["pages"], strict=True):
        proof = validate_transition(a, b, identity_bindings(a), [])
        old = {block["id"]: block for block in a["blocks"]}
        for block in b["blocks"]:
            if {k: v for k, v in block.items() if k != "relations"} != {
                k: v for k, v in old[block["id"]].items() if k != "relations"
            }:
                raise DemoError("SHARED_ATOM_CHANGED")
        coverage.append(proof)
    old = {r["id"]: r for r in before["relations"]}
    new = {r["id"]: r for r in after["relations"]}
    if len(old) != len(before["relations"]) or len(new) != len(after["relations"]):
        raise DemoError("RELATION_ID_DUPLICATED")
    source_ids = {b["id"] for p in after["pages"] for b in p["blocks"]}
    for rid, relation in old.items():
        if new.get(rid) != relation and not stage_owned(relation):
            raise DemoError("PROTECTED_RELATION_CHANGED")
    for rid, relation in new.items():
        if relation["from"] not in source_ids or relation["to"] not in source_ids:
            raise DemoError("RELATION_SOURCE_UNKNOWN")
        if old.get(rid) == relation:
            continue
        if not stage_owned(relation):
            raise DemoError("UNPROVEN_RELATION_DELTA")
        rejection = continuation_rejection(before, relation["from"], relation["to"])
        if rejection:
            raise DemoError(rejection)
    return {
        "schema_version": "shared-conservation/1",
        "atomic_coverage": coverage,
        "input_order": {str(p["page_index"]): p["reading_order"] for p in before["pages"]},
        "relations_before_sha256": json_hash(before["relations"]),
        "relations_after_sha256": json_hash(after["relations"]),
        "relation_delta": {
            "added": sorted(new.keys() - old.keys()),
            "removed": sorted(old.keys() - new.keys()),
            "updated": sorted(rid for rid in old.keys() & new.keys() if old[rid] != new[rid]),
        },
        "affected_source_ids": sorted(
            {r[key] for rid, r in new.items() if old.get(rid) != r for key in ("from", "to")}
        ),
    }
