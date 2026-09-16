"""Table, formula and relation scoring with explicit unsupported denominators."""

from __future__ import annotations

from collections import Counter
from itertools import pairwise
from typing import Any

from .formula import output_tree, reference_tree

Json = dict[str, Any]


def score_structure(
    observed: Json,
    units: list[Json],
    bound: dict[str, list[int]],
    block_anchor: dict[str, str],
    sources: Json,
    *,
    complete_relations: bool = False,
    unscored_math_nodes: set[tuple[int, int]] | None = None,
    image_preserved_unit_ids: set[str] | None = None,
    uncertain_formulas: list[Json] | None = None,
    uncertain_edges: list[Json] | None = None,
) -> tuple[Json, list[Json], set[int]]:
    """Score actual table grids, OMML and source-bound predicted edges."""
    from .metrics import _has_math_content, metric

    paragraphs = observed["paragraphs"]
    failures: list[Json] = []
    table_units = [
        u for u in units if u["kind"] == "table" and u["reference"].get("is_data_table", True)
    ]
    tables_correct = cells_correct = cells_total = cells_editable = 0
    repeated_header_cells = 0
    fallback_table_ids: list[str] = []
    fallback_formula_ids: list[str] = []
    fallback_cells = 0
    preserved = image_preserved_unit_ids or set()
    claimed: set[int] = set()
    seen_tables: set[int] = set()
    for u in table_units:
        ref = u["reference"]
        indexes = bound.get(ref["source_anchor_id"], [])
        tables = {paragraphs[i]["table"] for i in indexes} - {None}
        counted_cells = [
            c
            for c in ref["cells"]
            if not (ref.get("header_is_repeated") and c["row"] < ref.get("header_rows", 0))
        ]
        repeated_header_cells += len(ref["cells"]) - len(counted_cells)
        cells_total += len(counted_cells)
        table_paragraphs = [
            p for i, p in enumerate(paragraphs) if i in indexes or p["table"] in tables
        ]
        if u["unit_id"] in preserved and not any(
            p["text"].strip() or any(_has_math_content(m) for m in p["math"])
            for p in table_paragraphs
        ):
            fallback_table_ids.append(u["unit_id"])
            fallback_cells += len(counted_cells)
            continue
        actual: Json = {"rows": 0, "cols": 0, "cells": []}
        if len(tables) == 1:
            table_id = next(iter(tables))
            if table_id not in seen_tables:
                actual = observed["tables"][table_id]
                seen_tables.add(table_id)
                claimed.update(i for i, p in enumerate(paragraphs) if p["table"] == table_id)

        def topology(c: Json) -> tuple[int, int, int, int]:
            return c["row"], c["col"], c["rowspan"], c["colspan"]

        correct = (
            actual["rows"] == ref["rows"]
            and actual["cols"] == ref["cols"]
            and sorted(map(topology, actual["cells"])) == sorted(map(topology, ref["cells"]))
        )
        tables_correct += correct
        by_position = {(c["row"], c["col"]): c for c in actual["cells"]}
        for cell in counted_cells:
            found = by_position.get((cell["row"], cell["col"]))
            cells_editable += found is not None
            cells_correct += found is not None and found["text"] == cell["text"]
        if not correct or any(
            by_position.get((c["row"], c["col"]), {}).get("text") != c["text"] for c in ref["cells"]
        ):
            failures.append({"unit_id": u["unit_id"], "page": u["page"], "code": "TABLE_MISMATCH"})
    formulas = [u for u in units if u["kind"] == "formula"]
    all_maths = {(i, j) for i, p in enumerate(paragraphs) for j in range(len(p["math"]))}
    actual_trees = {node: output_tree(paragraphs[node[0]]["math"][node[1]]) for node in all_maths}

    def nodes_for(unit: Json) -> list[tuple[int, int]]:
        reference = unit.get("reference")
        indexes = (
            bound.get(reference.get("source_anchor_id", ""), [])
            if isinstance(reference, dict)
            else []
        )
        return sorted({(i, j) for i in indexes for j in range(len(paragraphs[i]["math"]))})

    expected_trees = {i: reference_tree(u["reference"]["text"]) for i, u in enumerate(formulas)}
    supported = sum(tree is not None for tree in expected_trees.values())
    candidates = {
        i: [node for node in nodes_for(formulas[i]) if actual_trees[node] == tree]
        for i, tree in expected_trees.items()
        if tree is not None
    }
    owners: dict[tuple[int, int], int] = {}

    def allocate(index: int, visited: set[tuple[int, int]]) -> bool:
        for node in candidates[index]:
            if node not in owners:
                owners[node] = index
                return True
        for node in candidates[index]:
            if node in visited:
                continue
            visited.add(node)
            if allocate(owners[node], visited):
                owners[node] = index
                return True
        return False

    for index in candidates:
        allocate(index, set())
    matched_units = set(owners.values())
    consumed_maths = set(owners)
    present_formula_ids = {formulas[i]["unit_id"] for i in matched_units}
    formula_correct = len(matched_units)

    def claim_remaining(unit: Json) -> bool:
        node = next(
            (
                node
                for node in nodes_for(unit)
                if node not in consumed_maths
                and _has_math_content(paragraphs[node[0]]["math"][node[1]])
            ),
            None,
        )
        if node is None:
            return False
        consumed_maths.add(node)
        present_formula_ids.add(unit["unit_id"])
        return True

    for index, unit in enumerate(formulas):
        if expected_trees[index] is None or index in matched_units:
            continue
        present = claim_remaining(unit)
        if not present and unit["unit_id"] in preserved:
            fallback_formula_ids.append(unit["unit_id"])
        else:
            failures.append(
                {"unit_id": unit["unit_id"], "page": unit["page"], "code": "FORMULA_MISMATCH"}
            )
    for index, unit in enumerate(formulas):
        if expected_trees[index] is None:
            claim_remaining(unit)
    for unit in uncertain_formulas or []:
        claim_remaining(unit)
    edges = [u for u in units if u["kind"] == "figure_edge"]
    predicted: list[tuple[str | None, str | None, str]] = []
    for edge in sources.get("relations", []):
        left, right = block_anchor.get(edge["from"]), block_anchor.get(edge["to"])
        predicted.append((left, right, edge["type"]))
    expected_edges = {
        (u["reference"]["from"], u["reference"]["to"], u["reference"]["relation"]) for u in edges
    }
    uncertain_remaining = Counter(
        (u["reference"]["from"], u["reference"]["to"], u["reference"]["relation"])
        for u in uncertain_edges or []
        if isinstance(u.get("reference"), dict)
        and all(k in u["reference"] for k in ("from", "to", "relation"))
    )
    matched_edges = set()
    excluded_edges = 0
    unknown_edges = 0
    for edge in predicted:
        if (
            not complete_relations
            and edge not in expected_edges
            and edge not in uncertain_remaining
        ):
            unknown_edges += 1
            continue
        if not bound.get(edge[0] or "") or not bound.get(edge[1] or ""):
            continue
        if edge in expected_edges:
            matched_edges.add(edge)
        elif uncertain_remaining[edge]:
            uncertain_remaining[edge] -= 1
            excluded_edges += 1
    # A reference edge is consumed once; repeated predictions remain in the denominator.
    correct_edges = covered = len(matched_edges)
    for u in edges:
        ref = u["reference"]
        key = (ref["from"], ref["to"], ref["relation"])
        if key not in predicted or not bound.get(ref["from"]) or not bound.get(ref["to"]):
            failures.append(
                {"unit_id": u["unit_id"], "page": u["page"], "code": "FIGURE_EDGE_MISMATCH"}
            )
    order_total = order_correct = order_missing = 0
    for u in [u for u in units if u["kind"] == "reading_order"]:
        anchors = u["reference"]["anchors"]
        for left, right in pairwise(anchors):
            order_total += 1
            a, b = bound.get(left, []), bound.get(right, [])
            if not a or not b or set(a) & set(b):
                order_missing += 1
            elif max(a) < min(b):
                order_correct += 1
            else:
                failures.append(
                    {"unit_id": u["unit_id"], "page": u["page"], "code": "READING_ORDER_MISMATCH"}
                )
    metrics = {
        "tables": metric(
            len(table_units), len(table_units) - len(fallback_table_ids), tables_correct
        ),
        "table_cells": metric(cells_total, cells_total - fallback_cells, cells_correct),
        "table_editable": metric(cells_total, cells_total, cells_editable),
        "formulas": metric(len(formulas), supported - len(fallback_formula_ids), formula_correct),
        "relation_precision": metric(
            len(predicted),
            len(predicted) - excluded_edges - unknown_edges,
            correct_edges,
            excluded_edges,
        ),
        "relation_coverage": metric(len(edges), len(edges), covered),
        "reading_order": metric(order_total, order_total - order_missing, order_correct),
    }
    # Keep eligible/unscored diagnostics, but precision only divides scored predictions.
    precision = metrics["relation_precision"]
    precision["unknown_count"] = unknown_edges
    precision["value"] = (
        correct_edges / precision["scored_count"] if precision["scored_count"] else None
    )
    continuation_ids = {
        u["reference"]["logical_table_id"]
        for u in table_units
        if u["reference"].get("segment_count", 1) > 1
    }
    metrics["tables"]["fallback_count"] = len(fallback_table_ids)
    metrics["tables"]["fallback_unit_ids"] = fallback_table_ids
    metrics["formulas"]["fallback_count"] = len(fallback_formula_ids)
    metrics["tables"]["continuation"] = metric(len(continuation_ids), 0, 0)
    metrics["table_cells"]["repeated_header_cells_excluded"] = repeated_header_cells
    metrics["formulas"]["unmatched_output_count"] = len(
        all_maths - consumed_maths - (unscored_math_nodes or set())
    )
    metrics["formulas"]["present_unit_ids"] = sorted(present_formula_ids)
    metrics["formulas"]["unsupported_count"] = len(formulas) - supported
    metrics["formulas"]["supported_coverage"] = metric(supported, supported, formula_correct)
    metrics["reading_order"]["missing_count"] = order_missing
    metrics["reading_order"]["incorrect_count"] = order_total - order_missing - order_correct
    return metrics, failures, claimed
