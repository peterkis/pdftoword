"""Bounded classification figures need real frames, directed links and owned glyphs."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from prototypes.docx_output.common import Json
from prototypes.docx_output.native_diagram import diagram_regions


def scene() -> tuple[list[Json], list[Json], Json]:
    objects = []
    for i, x in enumerate([0, 60]):
        objects.append(
            {
                "id": f"f{i}",
                "type": 2,
                "stroke_rect": [x, 0, x + 30, 40],
                "bbox": [x - 0.5, -0.5, x + 30.5, 40.5],
                "stroke_width_pt": 1,
            }
        )
    for name, points in [("shaft", [[30, 20], [60, 20]]), ("head", [[53, 15], [60, 20]])]:
        objects.append(
            {
                "id": name,
                "type": 2,
                "solid_line": points,
                "stroke_width_pt": 1,
                "bbox": [
                    min(p[0] for p in points) - 0.5,
                    min(p[1] for p in points) - 0.5,
                    max(p[0] for p in points) + 0.5,
                    max(p[1] for p in points) + 0.5,
                ],
            }
        )
    chars = [
        {"source_id": f"r{i}", "text": "Label", "bbox": [x + 3, 5, x + 23, 15]}
        for i, x in enumerate([0, 60])
    ]
    glyphs = [
        {"index": i, "text": "L", "bbox": c["bbox"], "generated": False, "visibility": "painted"}
        for i, c in enumerate(chars)
    ]
    bindings = {
        c["source_id"]: {
            "status": "VERIFIED",
            "bbox": c["bbox"],
            "char_indices": [i],
            "paint_orders": [10 + i],
        }
        for i, c in enumerate(chars)
    }
    return objects, chars, {"glyphs": glyphs, "runs": bindings}


def test_single_wing_direction_and_candidates_are_preserved() -> None:
    objects, chars, ev = scene()
    before = copy.deepcopy((objects, chars, ev))
    regions = diagram_regions(objects, chars, ev)
    assert len(regions) == 1
    assert regions[0]["edges"][0]["from"] == "f0"
    assert regions[0]["edges"][0]["to"] == "f1"
    assert regions[0]["native_run_ids"] == ["r0", "r1"]
    assert (objects, chars, ev) == before


@pytest.mark.parametrize(
    "fault", ["no_head", "no_link", "unknown", "outside_text", "cross_frame", "reuse", "ambiguous"]
)
def test_unproven_graph_abstains(fault: str) -> None:
    objects, chars, ev = scene()
    if fault == "no_head":
        objects = objects[:-1]
    elif fault == "no_link":
        objects = objects[:2]
    elif fault == "unknown":
        objects.append({"id": "u", "type": 3, "bbox": [35, 15, 40, 25]})
    elif fault == "outside_text":
        ev["glyphs"].append(
            {
                "index": 99,
                "text": "X",
                "bbox": [35, 15, 40, 25],
                "generated": False,
                "visibility": "painted",
            }
        )
    elif fault == "cross_frame":
        ev["runs"]["r0"]["bbox"] = [25, 5, 35, 15]
    elif fault == "reuse":
        ev["runs"]["r1"]["char_indices"] = [0]
    else:
        extra = copy.deepcopy(objects[-1])
        extra["id"] = "secondhead"
        objects.append(extra)
    assert diagram_regions(objects, chars, ev) == []


@pytest.mark.parametrize("profile", ["legacy", "fidelity-v3.1"])
def test_real_native_diagram_docx_and_caption(tmp_path: Path, profile: str) -> None:
    import shutil
    import uuid

    from prototypes.docx_output.common import PRIVATE, read
    from prototypes.docx_output.pipeline import convert
    from tests.demo.synthetic import make_pdf

    commands = [
        "0 0 0 RG 1 w 60 260 60 60 re S 170 260 60 60 re S",
        "120 280 m 170 280 l S 162 287 m 170 280 l S",
        "170 290 m 120 290 l S 128 283 m 120 290 l S",
    ]
    for x, y, text in [(70, 300, "Alpha"), (180, 300, "Beta"), (100, 240, "图1 分类图")]:
        commands.append(f"BT /F1 9 Tf {x} {y} Td <{text.encode('utf-16-be').hex()}> Tj ET")
    source = tmp_path / "diagram.pdf"
    make_pdf(source, decoration="\n".join(commands).encode())
    root = PRIVATE / ("diagram-test-" + uuid.uuid4().hex)
    try:
        job = convert(source, mode="native", output_profile=profile, output_root=root)
        ir = read(job / "layout.auto.json")
        diagrams = [
            b for b in ir["pages"][0]["blocks"] if "native_diagram_image_fallback" in b["flags"]
        ]
        assert len(diagrams) == 1
        b = diagrams[0]
        assert len(b["content_candidates"][0]["evidence"]["edges"]) == 2
        assert any(e["type"] == "caption_of" and e["to"] == b["id"] for e in ir["relations"])
        assert not any(e["type"] == "references" and e["from"] == b["id"] for e in ir["relations"])
        source_record = next(
            r for r in read(job / "source-map.auto.json")["blocks"] if r["block_id"] == b["id"]
        )
        assert source_record["fallback"] and source_record["images"][0]["fallback"]
    finally:
        shutil.rmtree(root, ignore_errors=True)
