"""Auditable precedence DAG; source order breaks unconstrained ties, never overrides edges."""

from __future__ import annotations

import heapq
from collections import Counter

from ..common import Json


def resolve_order(source_order: list[str], edges: list[Json]) -> Json:
    """Return a complete topological order or an explicit cycle/endpoint abstention."""
    if any(n != 1 for n in Counter(source_order).values()):
        return {"status": "ABSTAIN", "reason": "DUPLICATE_ORDER_NODE", "order": source_order}
    rank = {bid: i for i, bid in enumerate(source_order)}
    outgoing: dict[str, set[str]] = {bid: set() for bid in source_order}
    incoming = dict.fromkeys(source_order, 0)
    for edge in edges:
        a, b = edge["from"], edge["to"]
        if a not in rank or b not in rank:
            return {"status": "ABSTAIN", "reason": "ORDER_ENDPOINT_MISSING", "order": source_order}
        if b not in outgoing[a]:
            outgoing[a].add(b)
            incoming[b] += 1
    ready = [rank[bid] for bid in source_order if not incoming[bid]]
    heapq.heapify(ready)
    selected = []
    while ready:
        bid = source_order[heapq.heappop(ready)]
        selected.append(bid)
        for other in sorted(outgoing[bid], key=rank.__getitem__):
            incoming[other] -= 1
            if not incoming[other]:
                heapq.heappush(ready, rank[other])
    if len(selected) != len(source_order):
        return {
            "status": "ABSTAIN",
            "reason": "ORDER_DAG_CYCLE",
            "order": source_order,
            "unresolved_nodes": [bid for bid in source_order if incoming[bid]],
        }
    return {"status": "PROVEN", "order": selected, "edges": edges, "engine_confidence": None}
