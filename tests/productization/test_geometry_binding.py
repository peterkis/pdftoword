"""Exact source conservation independently of candidate geometry and output IDs."""

from __future__ import annotations

import copy
from itertools import pairwise
from typing import Any

import pytest
from prototypes.docx_output.common import DemoError, block
from prototypes.docx_output.geometry.binding import (
    identity_bindings,
    inventory,
    validate_transition,
)


def page(texts: list[str]) -> dict[str, Any]:
    blocks = [
        block(f"b{i}", 0, [0, i * 10, 20, i * 10 + 8], text, "native_pdf")
        for i, text in enumerate(texts)
    ]
    return {"page_index": 0, "blocks": blocks, "reading_order": [b["id"] for b in blocks]}


def edges(order: list[str]) -> list[list[str]]:
    return [[a, b] for a, b in pairwise(order)]


def test_explicit_column_order_preserves_atoms() -> None:
    before = page(["A", "D", "B", "E", "C", "F"])
    projected = copy.deepcopy(before)
    projected["reading_order"] = ["b0", "b2", "b4", "b1", "b3", "b5"]
    proof = validate_transition(
        before, projected, identity_bindings(before), edges(projected["reading_order"])
    )
    assert proof["atomic_coverage"] == "EXACT"
    assert proof["geometry_support"] == "NOT_EVALUATED"
    assert proof["inventory"]["input_order"] == before["reading_order"]
    assert before["reading_order"] == ["b0", "b1", "b2", "b3", "b4", "b5"]


def test_split_and_merge_exact_spans() -> None:
    before = page(["Aβ 12", "中文\nend"])
    projected = page(["Aβ", " 12中文\nend"])
    projected["blocks"][0]["id"] = "left"
    projected["blocks"][1]["id"] = "right"
    projected["reading_order"] = ["left", "right"]
    bindings = {
        "left": [{"source_id": "b0", "start": 0, "end": 2}],
        "right": [
            {"source_id": "b0", "start": 2, "end": 5},
            {"source_id": "b1", "start": 0, "end": 6},
        ],
    }
    result = validate_transition(
        before,
        projected,
        bindings,
        [["left", "right"]],
        scopes={"b0": "question1/column1", "b1": "question1/column1"},
    )
    assert result["atomic_coverage"] == "EXACT"
    with pytest.raises(DemoError, match="MERGE_SCOPE"):
        validate_transition(
            before,
            projected,
            bindings,
            [["left", "right"]],
            scopes={"b0": "question1/column1", "b1": "question2/column1"},
        )


@pytest.mark.parametrize(
    "fault", ["missing", "duplicate", "changed", "bool", "unknown", "page", "runs"]
)
def test_invalid_projection_is_rejected(fault: str) -> None:
    before = page(["identical", "identical"])
    projected = copy.deepcopy(before)
    bindings = identity_bindings(before)
    if fault == "missing":
        bindings["b1"][0]["end"] = 8
        projected["blocks"][1]["content"]["plain_text"] = "identica"
    elif fault == "duplicate":
        bindings["b1"][0]["source_id"] = "b0"
    elif fault == "changed":
        projected["blocks"][0]["content"]["plain_text"] = "corrected"
    elif fault == "bool":
        bindings["b0"][0]["start"] = False
    elif fault == "unknown":
        bindings["b0"][0]["source_id"] = "other-page"
    elif fault == "runs":
        projected["blocks"][0]["content"]["runs"] = [{"text": "different"}]
    else:
        projected["page_index"] = 1
    with pytest.raises(DemoError):
        validate_transition(before, projected, bindings, [])


def test_empty_source_cannot_be_duplicated() -> None:
    before = page([""])
    projected = page(["", ""])
    bindings = {bid: [{"source_id": "b0", "start": 0, "end": 0}] for bid in ["b0", "b1"]}
    with pytest.raises(DemoError, match="COVERAGE"):
        validate_transition(before, projected, bindings, [["b0", "b1"]])


@pytest.mark.parametrize("fault", ["bbox", "split", "order"])
def test_manual_lock_includes_position_and_anchor(fault: str) -> None:
    before = page(["locked", "other"])
    before["blocks"][0]["flags"].append("manual_lock")
    projected = copy.deepcopy(before)
    bindings = identity_bindings(before)
    if fault == "bbox":
        projected["blocks"][0]["bbox"] = [0, 0, 50, 50]
    elif fault == "split":
        projected["blocks"][0]["id"] = "replacement"
        projected["reading_order"][0] = "replacement"
        bindings["replacement"] = bindings.pop("b0")
    else:
        projected["reading_order"].reverse()
    with pytest.raises(DemoError, match="MANUAL_LOCK"):
        validate_transition(before, projected, bindings, edges(projected["reading_order"]))


@pytest.mark.parametrize("proof", [[], [["b0", "b1"]], [["b1", "b0"], ["b0", "b1"]]])
def test_reorder_requires_sufficient_acyclic_evidence(proof: list[list[str]]) -> None:
    before = page(["A", "B"])
    projected = copy.deepcopy(before)
    projected["reading_order"].reverse()
    with pytest.raises(DemoError, match="ORDER"):
        validate_transition(before, projected, identity_bindings(before), proof)


def test_image_atom_not_replaced_or_dropped() -> None:
    before = page(["figure"])
    before["blocks"][0]["content"] = {"kind": "image", "asset_id": "source-figure"}
    projected = copy.deepcopy(before)
    assert (
        validate_transition(before, projected, identity_bindings(before), [])["atomic_coverage"]
        == "EXACT"
    )
    projected["blocks"][0]["content"]["asset_id"] = "different-figure"
    with pytest.raises(DemoError, match="NON_TEXT"):
        validate_transition(before, projected, identity_bindings(before), [])


def test_inventory_rejects_duplicate_ids() -> None:
    before = page(["A", "B"])
    before["blocks"][1]["id"] = "b0"
    with pytest.raises(DemoError, match="INVENTORY"):
        inventory(before)
