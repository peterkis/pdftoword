"""Only a complete stroked lattice may own native text for local image fallback."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from prototypes.docx_output.common import Json
from prototypes.docx_output.native_grid import ruled_regions


def evidence() -> tuple[list[Json], list[Json]]:
    objects = []
    for axis in ("h", "v"):
        for i in range(3):
            a, b = ([0, i * 20], [40, i * 20]) if axis == "h" else ([i * 20, 0], [i * 20, 40])
            objects.append(
                {
                    "id": f"{axis}{i}",
                    "type": 2,
                    "bbox": [
                        min(a[0], b[0]) - 0.5,
                        min(a[1], b[1]) - 0.5,
                        max(a[0], b[0]) + 0.5,
                        max(a[1], b[1]) + 0.5,
                    ],
                    "solid_line": [a, b],
                }
            )
    chars = [
        {"source_id": f"r{x}{y}", "text": f"{x}{y}", "bbox": [x + 3, y + 3, x + 10, y + 12]}
        for y in (0, 20)
        for x in (0, 20)
    ]
    return objects, chars


def test_grid_preserves_every_run_with_explicit_cell_evidence() -> None:
    objects, chars = evidence()
    before = copy.deepcopy((objects, chars))
    regions = ruled_regions(objects, chars)
    assert len(regions) == 1
    region = regions[0]
    assert region["native_run_ids"] == [c["source_id"] for c in chars]
    assert len(region["cells"]) == 4
    assert len(region["path_ids"]) == 6
    assert (objects, chars) == before


@pytest.mark.parametrize("damage", ["frame", "broken", "curve", "crossing", "image", "empty"])
def test_bbox_containment_alone_never_owns_text(damage: str) -> None:
    objects, chars = evidence()
    if damage == "frame":
        objects = [o for o in objects if o["id"] not in ("h1", "v1")]
    elif damage == "broken":
        objects[1]["bbox"][2] = 15
        objects[1]["solid_line"][1][0] = 15
    elif damage == "curve":
        del objects[1]["solid_line"]
    elif damage == "crossing":
        chars[0]["bbox"][2] = 25
    elif damage == "image":
        objects.append({"id": "image", "type": 3, "bbox": [2, 2, 10, 10]})
    else:
        chars.pop()
    assert ruled_regions(objects, chars) == []


def test_body_overlapping_only_outer_stroke_is_not_claimed() -> None:
    objects, chars = evidence()
    chars.append({"source_id": "body", "text": "Body", "bbox": [2, 40.2, 30, 50]})
    region = ruled_regions(objects, chars)[0]
    assert "body" not in region["native_run_ids"]


@pytest.mark.parametrize("profile", ["legacy", "fidelity-v3.1"])
def test_native_docx_has_one_crop_and_preserves_candidates(tmp_path: Path, profile: str) -> None:
    import shutil
    import uuid

    from docx import Document
    from prototypes.docx_output.common import PRIVATE, read
    from prototypes.docx_output.pipeline import convert
    from tests.demo.synthetic import make_pdf

    commands = ["0 0 0 RG 1 w"]
    for y in (200, 230, 260):
        commands.append(f"60 {y} m 260 {y} l S")
    for x in (60, 160, 260):
        commands.append(f"{x} 200 m {x} 260 l S")
    for x, y, text in (
        (70, 240, "CellA"),
        (170, 240, "CellB"),
        (70, 210, "CellC"),
        (170, 210, "CellD"),
        (70, 175, "AfterGrid"),
    ):
        commands.append(f"BT /F1 10 Tf {x} {y} Td <{text.encode('utf-16-be').hex()}> Tj ET")
    pdf = tmp_path / "grid.pdf"
    make_pdf(pdf, decoration="\n".join(commands).encode())
    root = PRIVATE / ("grid-test-" + uuid.uuid4().hex)
    try:
        job = convert(pdf, mode="native", output_profile=profile, output_root=root)
        ir = read(job / "layout.auto.json")
        grids = [b for b in ir["pages"][0]["blocks"] if "ruled_grid_image_fallback" in b["flags"]]
        assert len(grids) == 1
        grid = grids[0]
        assert grid["render_policy"] == "preserve_image"
        candidate = grid["content_candidates"][0]
        assert len(candidate["evidence"]["native_runs"]) == 4
        assert len(candidate["evidence"]["cells"]) == 4
        doc = Document(str(job / "auto.docx"))
        body = "\n".join(p.text for p in doc.paragraphs)
        assert "AfterGrid" in body and "CellA" not in body
        assert len(doc.inline_shapes) == 2  # existing fixture figure plus one entire grid
        mapping = read(job / "source-map.auto.json")
        assert any(b["block_id"] == grid["id"] and b["fallback"] for b in mapping["blocks"])
    finally:
        shutil.rmtree(root, ignore_errors=True)
