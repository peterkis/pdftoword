"""Table, formula and relation scoring with explicit unsupported denominators."""

from __future__ import annotations

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
    supported = formula_correct = 0
    bound_maths = {
        (i, j)
        for u in formulas
        for i in bound.get(u["reference"]["source_anchor_id"], [])
        for j in range(len(paragraphs[i]["math"]))
    }
    bound_maths.update(unscored_math_nodes or set())
    all_maths = {(i, j) for i, p in enumerate(paragraphs) for j in range(len(p["math"]))}
    consumed_maths: set[tuple[int, int]] = set()
    for u in formulas:
        ref = u["reference"]
        expected = reference_tree(ref["text"])
        if expected is None:
            continue
        supported += 1
        indexes = bound.get(ref["source_anchor_id"], [])
        maths = [m for i in indexes for m in paragraphs[i]["math"]]
        if u["unit_id"] in preserved and not any(_has_math_content(m) for m in maths):
            fallback_formula_ids.append(u["unit_id"])
            continue
        nodes = {(i, j) for i in indexes for j in range(len(paragraphs[i]["math"]))}
        correct = (
            len(maths) == 1
            and not nodes.intersection(consumed_maths)
            and output_tree(maths[0]) == expected
        )
        consumed_maths.update(nodes)
        formula_correct += correct
        if not correct:
            failures.append(
                {"unit_id": u["unit_id"], "page": u["page"], "code": "FORMULA_MISMATCH"}
            )
    edges = [u for u in units if u["kind"] == "figure_edge"]
    predicted: list[tuple[str | None, str | None, str]] = []
    for edge in sources.get("relations", []):
        left, right = block_anchor.get(edge["from"]), block_anchor.get(edge["to"])
        predicted.append((left, right, edge["type"]))
    expected_edges = {
        (u["reference"]["from"], u["reference"]["to"], u["reference"]["relation"]) for u in edges
    }
    correct_edges = sum(
        e in expected_edges and bool(bound.get(e[0] or "")) and bool(bound.get(e[1] or ""))
        for e in predicted
    )
    covered = len(
        {
            e
            for e in predicted
            if e in expected_edges and bound.get(e[0] or "") and bound.get(e[1] or "")
        }
    )
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
            len(predicted), len(predicted) if edges or complete_relations else 0, correct_edges
        ),
        "relation_coverage": metric(len(edges), len(edges), covered),
        "reading_order": metric(order_total, order_total - order_missing, order_correct),
    }
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
    metrics["formulas"]["unmatched_output_count"] = len(all_maths - bound_maths)
    metrics["formulas"]["unsupported_count"] = len(formulas) - supported
    metrics["formulas"]["supported_coverage"] = metric(supported, supported, formula_correct)
    metrics["reading_order"]["missing_count"] = order_missing
    metrics["reading_order"]["incorrect_count"] = order_total - order_missing - order_correct
    return metrics, failures, claimed
