"""Native evidence preparation and actual public continuation boundary probes."""

from __future__ import annotations

import copy
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from prototypes.docx_output.common import PRIVATE
from prototypes.docx_output.planning.paragraphs import native_observations
from prototypes.docx_output.structure_processors.bridge import bridge
from prototypes.docx_output.structure_processors.docvortex import DocVortexStructureProcessor
from tests.productization.test_shared_structure_actual import continuation_ir, text_ir


@pytest.fixture
def case() -> Iterator[Path]:
    root = PRIVATE / ("native-reflow-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root)


@pytest.mark.parametrize("separation", [0, 150])
def test_native_runs_frozen_without_manufactured_lines(case: Path, separation: int) -> None:
    ir = text_ir(case, "a-b²")
    b = ir["pages"][0]["blocks"][0]
    b["type"] = "paragraph"
    run = {
        "text": "a-",
        "bbox": [10, 10, 30, 20],
        "font_family": "FontA",
        "font_size_pt": 11,
        "bold": False,
        "italic": False,
        "underline": False,
        "superscript": False,
        "subscript": False,
        "color": None,
        "confidence": 0,
        "source_ref": b["id"],
    }
    second = {
        **run,
        "text": "b²",
        "bbox": [30 + separation, 10, 50 + separation, 20],
        "font_family": "FontB",
    }
    b["content"]["runs"] = [run, second]
    before = copy.deepcopy(ir)
    result = native_observations(ir)
    assert ir == before and result["pages"] == before["pages"]
    entry = result["metadata"]["native_observation_ledger"]["entries"][0]
    assert len(set(entry["source_span_ids"])) == 2
    assert entry["source_block"] == b
    if separation:
        assert entry["status"] == "NATIVE_REGION_REQUIRES_PARTITION"
        assert b["id"] not in result["metadata"]["structure_evidence"]
    else:
        assert entry["line_count"] == 1
        assert result["metadata"]["structure_evidence"][b["id"]]["lines"][0]["text"] == "a-b²"


def test_no_runs_do_not_become_fake_lines(case: Path) -> None:
    ir = text_ir(case)
    result = native_observations(ir)
    assert (
        result["metadata"]["native_observation_ledger"]["entries"][0]["status"] == "NO_RUN_EVIDENCE"
    )
    assert not result["metadata"]["structure_evidence"]


@pytest.mark.parametrize(
    "boundary", ["none", "question", "column", "manual_lock", "nonconsecutive"]
)
def test_public_continuation_and_explicit_boundaries(case: Path, boundary: str) -> None:
    ir = continuation_ir(case)
    if boundary in {"question", "column", "manual_lock"}:
        ir["metadata"]["structure_evidence"]["two"]["_paragraph_boundary"] = True
    if boundary == "question":
        ir["pages"][1]["blocks"][0]["type"] = "question"
    elif boundary == "manual_lock":
        ir["pages"][1]["blocks"][0]["flags"].append("manual_lock")
    elif boundary == "column":
        ir["pages"][0]["blocks"][0]["bbox"] = [60, 700, 280, 750]
        ir["pages"][1]["blocks"][0]["bbox"] = [320, 60, 540, 110]
        ir["metadata"]["structure_evidence"]["one"]["lines"] = [
            {"bbox": [60, 700, 280, 720]},
            {"bbox": [60, 730, 280, 750]},
        ]
        ir["metadata"]["structure_evidence"]["two"]["lines"] = [
            {"bbox": [320, 60, 540, 80]},
            {"bbox": [320, 90, 520, 110]},
        ]
    if boundary == "nonconsecutive":
        ir["pages"][1]["page_index"] = 3
        ir["pages"][1]["blocks"][0]["page_index"] = 3
        ir["source"]["page_count"] = 4
    if boundary in {"question", "column", "manual_lock"}:
        assert bridge(ir).model["pages"][1][0]["_paragraph_boundary"] is True
    processor = DocVortexStructureProcessor()
    result = processor.process(ir)
    actual = [r for r in result.document["relations"] if r["type"] == "continuation_of"]
    assert bool(actual) is (boundary == "none")
    assert processor.last_execution


def native_lines(case: Path, rows: list[tuple[str, list[float]]]) -> dict:
    """Independent exact native runs; fonts may have different resource tags."""
    from prototypes.docx_output.common import block

    ir = text_ir(case)
    blocks = []
    for i, (text, box) in enumerate(rows):
        b = block(f"atom-{i}", 0, box, text, "native_pdf", "paragraph")
        b["content"]["runs"] = [
            {
                "text": text,
                "bbox": box,
                "font_family": f"F{i}",
                "font_size_pt": 10,
                "bold": False,
                "italic": False,
                "underline": False,
                "superscript": False,
                "subscript": False,
                "color": None,
                "confidence": 0,
                "source_ref": b["id"],
            }
        ]
        blocks.append(b)
    ir["pages"][0]["blocks"] = blocks
    ir["pages"][0]["reading_order"] = [b["id"] for b in blocks]
    return ir


def test_native_paragraph_atom_conservation_and_first_indent(case: Path) -> None:
    from prototypes.docx_output.common import DemoError
    from prototypes.docx_output.planning.flow import plan_flow
    from prototypes.docx_output.planning.paragraphs import (
        build_native_paragraphs,
        verify_native_transition,
    )

    ir = native_lines(case, [("原字a-b²", [30, 10, 200, 20]), ("123续接", [10, 25, 200, 35])])
    before = copy.deepcopy(ir)
    result = build_native_paragraphs(ir)
    assert ir == before
    assert verify_native_transition(ir, result)["character_changes"] == 0
    b = result["pages"][0]["blocks"][0]
    assert len(result["pages"][0]["blocks"]) == 1
    assert b["content"]["plain_text"] == "原字a-b²123续接"
    assert (
        plan_flow(result, families=set()).output_layout["sections"][0]["nodes"][0][
            "first_line_indent_pt"
        ]
        == 20
    )
    result["pages"][0]["blocks"][0]["content"]["runs"][0]["text"] = "changed"
    with pytest.raises(DemoError, match="ATOM_CHANGED"):
        verify_native_transition(ir, result)


def test_native_two_columns_same_y_and_same_font_different_resource(case: Path) -> None:
    from prototypes.docx_output.planning.paragraphs import build_native_paragraphs

    ir = native_lines(
        case,
        [
            ("left-", [10, 10, 200, 20]),
            ("right-", [250, 10, 450, 20]),
            ("leftend", [10, 25, 200, 35]),
            ("rightend", [250, 25, 450, 35]),
        ],
    )
    result = build_native_paragraphs(ir)
    assert [b["content"]["plain_text"] for b in result["pages"][0]["blocks"]] == [
        "left-leftend",
        "right-rightend",
    ]


@pytest.mark.parametrize("boundary", ["question", "unspaced_question", "option", "lock", "figure"])
def test_automatic_native_boundaries(case: Path, boundary: str) -> None:
    from prototypes.docx_output.planning.paragraphs import (
        build_native_paragraphs,
        verify_native_transition,
    )

    text = (
        "2. new question"
        if boundary == "question"
        else "A) option"
        if boundary == "option"
        else "locked"
    )
    if boundary == "unspaced_question":
        text = "2.没有空格的题号"
    ir = native_lines(case, [("body", [10, 10, 200, 20]), (text, [10, 25, 200, 35])])
    if boundary == "lock":
        ir["pages"][0]["blocks"][1]["flags"].append("manual_lock")
    elif boundary == "figure":
        ir["pages"][0]["blocks"][1]["type"] = "caption"
    result = build_native_paragraphs(ir)
    assert len(result["pages"][0]["blocks"]) == 2
    assert verify_native_transition(ir, result)["status"] == "VERIFIED"


def test_native_hanging_indent_and_body_around_obstacle(case: Path) -> None:
    from prototypes.docx_output.planning.flow import plan_flow
    from prototypes.docx_output.planning.paragraphs import build_native_paragraphs

    ir = native_lines(
        case,
        [
            ("a) long list", [10, 10, 200, 20]),
            ("continuation", [30, 25, 200, 35]),
            ("caption", [10, 40, 200, 50]),
            ("body", [10, 55, 200, 65]),
        ],
    )
    ir["pages"][0]["blocks"][2]["type"] = "caption"
    result = build_native_paragraphs(ir)
    assert len(result["pages"][0]["blocks"]) == 3
    nodes = plan_flow(result, families=set()).output_layout["sections"][0]["nodes"]
    assert nodes[0]["first_line_indent_pt"] == -20
    assert result["pages"][0]["blocks"][1]["content"]["plain_text"] == "caption"
