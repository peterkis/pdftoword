"""Source-span conservation and explicit order proofs for geometry projections."""

from __future__ import annotations

from collections import Counter
from itertools import pairwise

from ..common import DemoError, Json
from ..structure_processors.bridge import json_hash
from ..structure_processors.docvortex import locked


def inventory(page: Json) -> Json:
    """Seal the input order and exact content without treating block IDs as output IDs."""
    blocks = page["blocks"]
    ids = [b["id"] for b in blocks]
    if len(set(ids)) != len(ids) or Counter(page["reading_order"]) != Counter(ids):
        raise DemoError("SOURCE_INVENTORY_INVALID")
    return {
        "schema_version": "content-inventory/1",
        "page_index": page["page_index"],
        "input_order": list(page["reading_order"]),
        "atoms": [
            {
                "source_id": b["id"],
                "content_sha256": json_hash(b["content"]),
                "text_length": len(b["content"]["plain_text"])
                if b["content"]["kind"] == "text"
                else None,
                "locked": locked(b),
            }
            for b in blocks
        ],
    }


def identity_bindings(page: Json) -> Json:
    """Bind unchanged blocks to their complete source, independently of output order."""
    return {
        b["id"]: [{"source_id": b["id"], "start": 0, "end": len(b["content"]["plain_text"])}]
        if b["content"]["kind"] == "text"
        else [{"source_id": b["id"]}]
        for b in page["blocks"]
    }


def validate_order(ids: list[str], order: list[str], edges: list[list[str]]) -> None:
    """An explicit topological order proves the supplied DAG is acyclic and covered."""
    if len(set(ids)) != len(ids) or Counter(order) != Counter(ids):
        raise DemoError("ORDER_COVERAGE_FAILED")
    if not isinstance(edges, list):
        raise DemoError("ORDER_DAG_VIOLATION")
    positions = {bid: i for i, bid in enumerate(order)}
    for edge in edges:
        if (
            not isinstance(edge, list)
            or len(edge) != 2
            or any(not isinstance(v, str) or v not in positions for v in edge)
            or positions[edge[0]] >= positions[edge[1]]
        ):
            raise DemoError("ORDER_DAG_VIOLATION")


def validate_transition(
    original: Json,
    projected: Json,
    bindings: Json,
    edges: list[list[str]],
    *,
    scopes: dict[str, str] | None = None,
) -> Json:
    """Prove exact source usage for split/merge/reorder without fabricating geometry.

    Text spans are Python string offsets, not estimates of physical glyph positions.
    A merge requires an explicit common scope for every source. This guard never
    supplies spans, geometry, column membership, or semantic order on its own.
    """
    sealed = inventory(original)
    if projected["page_index"] != original["page_index"]:
        raise DemoError("CROSS_PAGE_BINDING_REJECTED")
    source = {b["id"]: b for b in original["blocks"]}
    targets = {b["id"]: b for b in projected["blocks"]}
    validate_order([b["id"] for b in projected["blocks"]], projected["reading_order"], edges)
    if projected["reading_order"] != original["reading_order"]:
        proven = {tuple(edge) for edge in edges}
        if any((a, b) not in proven for a, b in pairwise(projected["reading_order"])):
            raise DemoError("CHANGED_ORDER_UNPROVEN")
    if set(bindings) != set(targets):
        raise DemoError("BINDING_TARGET_COVERAGE_FAILED")
    used: dict[str, list[tuple[int, int]]] = {bid: [] for bid in source}
    images: Counter[str] = Counter()
    locks: dict[str, str] = {}
    for bid, target in targets.items():
        spans = bindings[bid]
        if not isinstance(spans, list) or not spans:
            raise DemoError("BINDING_SOURCE_REQUIRED")
        source_ids: list[str] = [
            span["source_id"]
            for span in spans
            if isinstance(span, dict) and isinstance(span.get("source_id"), str)
        ]
        if len(source_ids) != len(spans) or any(sid not in source for sid in source_ids):
            raise DemoError("BINDING_SOURCE_UNKNOWN")
        distinct = set(source_ids)
        if len(distinct) > 1 and (
            scopes is None
            or any(sid not in scopes for sid in distinct)
            or len({scopes[sid] for sid in distinct}) != 1
        ):
            raise DemoError("MERGE_SCOPE_UNPROVEN")
        if (
            target["content"]["kind"] == "text"
            and target["content"].get("runs")
            and (
                "".join(run["text"] for run in target["content"]["runs"])
                != target["content"]["plain_text"]
            )
        ):
            raise DemoError("RUN_TEXT_MISMATCH")
        assembled = []
        for span in spans:
            sid = span["source_id"]
            atom = source[sid]
            if locked(atom):
                if len(spans) != 1 or bid != sid or target != atom:
                    raise DemoError("MANUAL_LOCK_CHANGED")
                locks[sid] = bid
            if atom["content"]["kind"] == "text":
                text = atom["content"]["plain_text"]
                start, end = span.get("start"), span.get("end")
                if (
                    type(start) is not int
                    or type(end) is not int
                    or not 0 <= start <= end <= len(text)
                    or (start == end and text)
                ):
                    raise DemoError("INVALID_SOURCE_SPAN")
                assembled.append(text[start:end])
                used[sid].append((start, end))
            else:
                if (
                    len(spans) != 1
                    or set(span) != {"source_id"}
                    or atom["content"] != target["content"]
                ):
                    raise DemoError("NON_TEXT_ATOM_CHANGED")
                images[sid] += 1
        if assembled and (
            target["content"]["kind"] != "text"
            or target["content"]["plain_text"] != "".join(assembled)
        ):
            raise DemoError("CONTENT_CHARACTER_CHANGED")
    for sid, atom in source.items():
        if atom["content"]["kind"] != "text":
            if images[sid] != 1:
                raise DemoError("NON_TEXT_COVERAGE_FAILED")
            continue
        if not atom["content"]["plain_text"] and used[sid] != [(0, 0)]:
            raise DemoError("TEXT_COVERAGE_GAP_OR_DUPLICATE")
        cursor = 0
        for start, end in sorted(used[sid]):
            if start != cursor:
                raise DemoError("TEXT_COVERAGE_GAP_OR_DUPLICATE")
            cursor = end
        if not used[sid] or cursor != len(atom["content"]["plain_text"]):
            raise DemoError("TEXT_COVERAGE_GAP_OR_DUPLICATE")
    # A locked anchor cannot be crossed by other sources during reordering.
    old_positions = {bid: i for i, bid in enumerate(original["reading_order"])}
    new_positions = {bid: i for i, bid in enumerate(projected["reading_order"])}
    for locked_source, locked_target in locks.items():
        for target_id, spans in bindings.items():
            for span in spans:
                sid = span["source_id"]
                if sid == locked_source:
                    continue
                if (old_positions[sid] < old_positions[locked_source]) != (
                    new_positions[target_id] < new_positions[locked_target]
                ):
                    raise DemoError("MANUAL_LOCK_ORDER_CHANGED")
    return {
        "schema_version": "content-binding-proof/1",
        "inventory": sealed,
        "inventory_sha256": json_hash(sealed),
        "bindings": bindings,
        "order_edges": edges,
        "output_order": list(projected["reading_order"]),
        "atomic_coverage": "EXACT",
        "geometry_support": "NOT_EVALUATED",
    }


def validate_bound_projection(original_ir: Json, candidate_ir: Json, projected: Json) -> Json:
    """Admit changed IDs only at measured line boundaries and conserved source order.

    Split/merge plus simultaneous column reordering is deliberately not inferred:
    the atom sequence must stay in the original order for this projection step.
    """
    from ..common import union
    from ..structure_processors.conservation import source_scopes
    from .candidate import rectangle

    original = next(p for p in original_ir["pages"] if p["page_index"] == projected["page_index"])
    key = str(projected["page_index"])
    bindings = candidate_ir["metadata"]["source_bindings"][key]
    supports = candidate_ir["metadata"].get("geometry_support", {}).get(key, {})
    source = {b["id"]: b for b in original["blocks"]}
    targets = {b["id"]: b for b in projected["blocks"]}
    rank = {bid: i for i, bid in enumerate(original["reading_order"])}
    scopes = source_scopes(original_ir)
    scope_ids = {bid: str(scopes[bid]) for bid in source}
    atoms = []
    for bid in projected["reading_order"]:
        target = targets[bid]
        spans = bindings.get(bid, [])
        measured = []
        owners = []
        for span in spans:
            sid = span.get("source_id")
            if sid not in source:
                raise DemoError("BINDING_SOURCE_UNKNOWN")
            old = source[sid]
            if target["type"] != old["type"] or target.get("style_ref") != old.get("style_ref"):
                raise DemoError("SOURCE_STYLE_OR_ROLE_CHANGED")
            if old["content"]["kind"] != "text":
                if (
                    bid != sid
                    or target["content"] != old["content"]
                    or target["bbox"] != old["bbox"]
                ):
                    raise DemoError("NON_TEXT_ATOM_CHANGED")
                atoms.append((rank[sid], 0, 0))
                continue
            start, end = span.get("start"), span.get("end")
            if type(start) is not int or type(end) is not int:
                raise DemoError("INVALID_SOURCE_SPAN")
            atoms.append((rank[sid], start, end))
            unchanged = bid == sid and len(spans) == 1 and target["content"] == old["content"]
            if (
                locked(old)
                or old["geometry_source"] == "native_pdf"
                or old["content"].get("runs")
                or sid in original_ir["metadata"].get("inline_parts", {})
            ) and not unchanged:
                raise DemoError("MEASURED_OR_STYLED_ATOM_REQUIRES_PRESERVATION")
            support = supports.get(sid, {})
            if support.get("source_content_sha256") != json_hash(old["content"]):
                raise DemoError("CONTENT_SUPPORT_MISSING_OR_STALE")
            fragments = [
                f
                for f in support.get("line_fragments", [])
                if start <= f["source_span"][0] and f["source_span"][1] <= end
            ]
            if fragments:
                cursor = start
                for fragment in fragments:
                    a, b = fragment["source_span"]
                    if a != cursor or fragment["source_span_sha256"] != json_hash(
                        old["content"]["plain_text"][a:b]
                    ):
                        raise DemoError("SOURCE_LINE_SPAN_UNPROVEN")
                    measured.append(rectangle(fragment["bbox_pt"]))
                    cursor = b
                if cursor != end:
                    raise DemoError("SOURCE_LINE_SPAN_UNPROVEN")
            elif start == 0 and end == len(old["content"]["plain_text"]):
                measured.append(rectangle(support["bbox_pt"]))
            else:
                raise DemoError("SUBLINE_GEOMETRY_INTERPOLATION_FORBIDDEN")
            owners.append(sid)
            old_candidates = {
                c["id"]: {k: v for k, v in c.items() if k != "selected"}
                for c in old.get("content_candidates", [])
            }
            new_candidates = {
                c["id"]: {k: v for k, v in c.items() if k != "selected"}
                for c in target.get("content_candidates", [])
            }
            if any(new_candidates.get(cid) != value for cid, value in old_candidates.items()):
                raise DemoError("SOURCE_CONTENT_CANDIDATE_LOST")
        if measured:
            if rectangle(target["bbox"]) != union(measured):
                raise DemoError("PROJECTED_GEOMETRY_NOT_SOURCE_BOUND")
            if len(set(owners)) > 1:
                # Common horizontal support is required in addition to explicit
                # question scope; a merge cannot jump between columns.
                widths = [supports[sid]["bbox_pt"] for sid in owners]
                if min(b[2] for b in widths) - max(b[0] for b in widths) <= 0:
                    raise DemoError("MERGE_CROSS_COLUMN")
    if atoms != sorted(atoms):
        raise DemoError("SOURCE_SPAN_ORDER_CHANGED")
    removed = source.keys() - targets.keys()
    if any(r[k] in removed for r in original_ir["relations"] for k in ("from", "to")) or any(
        child in removed for b in source.values() for child in b.get("children", [])
    ):
        raise DemoError("RELATION_REMAP_REQUIRES_EXPLICIT_OWNERSHIP")
    proof = validate_transition(
        original,
        projected,
        bindings,
        [list(edge) for edge in pairwise(projected["reading_order"])],
        scopes=scope_ids,
    )
    proof["geometry_support"] = "MEASURED_LINE_BOUNDARIES"
    proof["order_basis"] = "conserved_source_span_sequence"
    return proof
