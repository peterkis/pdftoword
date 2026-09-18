"""Geometry contracts exercised through real adapters, backend and sealed replay."""

from __future__ import annotations

import copy
import json
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from PIL import Image
from prototypes.docx_output.common import PRIVATE, ROOT, digest, read, save
from prototypes.docx_output.geometry import monkey_adapter, native_adapter, pp_adapter
from prototypes.docx_output.geometry.candidate import TransformChain
from prototypes.docx_output.geometry_replay import replay
from prototypes.docx_output.input_analysis import inspect_page
from prototypes.docx_output.structure import recover_monkey
from tests.productization.synthetic.generate import pdf_bytes


def chain() -> TransformChain:
    return TransformChain((200, 100), (400, 200), (0, 0, 400, 200), (400, 200))


def chat(content: str, finish: str = "stop") -> dict[str, Any]:
    return {"choices": [{"finish_reason": finish, "message": {"content": content}}]}


def pp() -> dict[str, Any]:
    return {
        "result": {
            "layoutParsingResults": [
                {
                    "prunedResult": {
                        "width": 400,
                        "height": 200,
                        "model_settings": {"use_doc_preprocessor": False},
                        "parsing_res_list": [
                            {
                                "block_label": "table",
                                "block_bbox": [20, 30, 200, 100],
                                "block_content": "DO NOT COPY",
                                "block_order": 7,
                            }
                        ],
                        "overall_ocr_res": {
                            "rec_boxes": [[20, 30, 180, 50]],
                            "rec_texts": ["SECRET"],
                        },
                        "formula_res_list": [
                            {
                                "dt_polys": [[30, 60], [50, 60], [50, 90], [30, 90]],
                                "rec_formula": "SECRET",
                            }
                        ],
                    }
                }
            ]
        }
    }


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_native_crop_rotation_and_pixel_roundtrip(tmp_path: Path, rotation: int) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(
        pdf_bytes(b"BT /F1 14 Tf 30 340 Td (Title) Tj ET", crop=True, rotation=rotation)
    )
    observed = inspect_page(source, 0)
    g = observed.geometry
    output = native_adapter.adapt(observed.record(), 0, {})
    assert not output["rejections"] and output["geometry_candidates"]
    candidate = output["geometry_candidates"][0]
    assert candidate["quad_pt"] == observed.text_runs[0]["quad_pt"]
    assert candidate["granularity"] == "native_advance_em_run"
    assert "Title" not in json.dumps(output)
    t = TransformChain(
        (g.width, g.height),
        (g.width * 2, g.height * 2),
        (10, 20, g.width * 2 - 30, g.height * 2 - 40),
        (1000, 900),
        (15, 25, 35, 45),
    )
    for xy in ((15, 25), (965, 855), (210.23, 333.71)):
        pt = t.to_point(*xy)
        assert t.to_input(*pt) == pytest.approx(xy, abs=0.5)
        assert g.to_point(*g.to_pdf(*pt)) == pytest.approx(pt, abs=1e-8)
        # Integer crop boundary error is checked independently from float geometry.
        assert [round(v) for v in xy] == pytest.approx(t.to_input(*pt), abs=1)
    schema = read(ROOT / "specs/geometry-candidate.schema.json")
    Draft202012Validator(schema).validate(candidate)


@pytest.mark.parametrize(
    "raw",
    [
        [20, 10, 10, 20],
        [0, 0, 0, 5],
        [0, 0, 1001, 10],
        [0, 0, "10", 20],
        [False, 0, 10, 20],
        [0, 0, float("nan"), 20],
        [0, 0, float("inf"), 20],
        [0, 0, 10**500, 20],
        [0, 0, 10],
        None,
    ],
)
def test_bad_box_rejects_only_region(raw: Any) -> None:
    data = [{"label": "text", "bbox": raw}, {"label": "image", "bbox": [10, 20, 50, 60]}]
    output = monkey_adapter.adapt(chat(json.dumps(data)), 0, chain(), {})
    assert len(output["geometry_candidates"]) == len(output["rejections"]) == 1
    assert output["geometry_candidates"][0]["raw_output_index"] == 1


@pytest.mark.parametrize(
    "content",
    [
        "__import__('os').system('false')",
        "not a literal",
        "{}",
        "[" * 30 + "]" * 30,
        " " * (monkey_adapter.MAX_BYTES + 1),
        json.dumps([{}] * 10001),
    ],
)
def test_bounded_literal_parser(content: str) -> None:
    output = monkey_adapter.adapt(chat(content), 0, chain(), {})
    assert not output["geometry_candidates"] and output["rejections"]


@pytest.mark.parametrize("finish", ["length", "error", None])
def test_incomplete_response(finish: Any) -> None:
    assert monkey_adapter.adapt(chat("[]", finish), 0, chain(), {})["rejections"]


@pytest.mark.parametrize("serializer", [json.dumps, repr])
def test_literal_and_json_duplicates_unknown_order(serializer: Any) -> None:
    row = {"label": "text", "bbox": [10, 20, 50, 60], "unrelated": None}
    output = monkey_adapter.adapt(
        chat(serializer([row, row])), 0, chain(), {"prompt_fingerprint": "f"}
    )
    candidate = output["geometry_candidates"][0]
    assert len(output["rejections"]) == 1
    assert candidate["engine_confidence"] is None
    assert candidate["order_status"] == "unknown" and candidate["provider_order"] is None
    assert candidate["bbox_pt"] == [2, 2, 10, 6]
    Draft202012Validator(read(ROOT / "specs/geometry-candidate.schema.json")).validate(candidate)


def test_pp_content_excluded_and_actual_order_fields_retained() -> None:
    body = pp()
    before = copy.deepcopy(body)
    output = pp_adapter.adapt(body, 0, chain(), {})
    assert body == before
    assert not output["rejections"] and len(output["geometry_candidates"]) == 3
    encoded = json.dumps(output)
    assert "SECRET" not in encoded and "DO NOT COPY" not in encoded
    assert output["geometry_candidates"][0]["provider_order"] == {"block_order": 7}
    assert output["geometry_candidates"][1]["hierarchy_level"] == "line"
    for c in output["geometry_candidates"]:
        Draft202012Validator(read(ROOT / "specs/geometry-candidate.schema.json")).validate(c)
    del body["result"]["layoutParsingResults"][0]["prunedResult"]["model_settings"]
    assert pp_adapter.adapt(body, 0, chain(), {})["rejections"]


def test_unknown_units_and_padding_are_not_guessed() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_COORDINATE"):
        chain().quad([0, 0, 1, 1], "unknown")
    t = TransformChain((100, 100), (100, 100), (20, 10, 80, 90), (200, 200), (10, 10, 10, 10))
    with pytest.raises(ValueError, match="OUT_OF_INPUT"):
        t.quad([0, 0, 20, 20], "input_pixel")
    _, quad = t.quad([10, 10, 190, 190], "input_pixel")
    assert quad == [[20, 10], [80, 10], [80, 90], [20, 90]]


def test_compat_wrapper_never_changes_content_or_selects_geometry() -> None:
    page: dict[str, Any] = {
        "page_index": 0,
        "width_pt": 200,
        "height_pt": 100,
        "blocks": [{"content": "keep", "selected_candidate_id": "content-1"}],
        "reading_order": ["keep"],
    }
    ir = {"provenance": {"pages": {"0": {"pixel_size": [400, 200]}}}, "issues": []}
    before = copy.deepcopy(page)
    recover_monkey(ir, page, {"monkey": chat('[{"label":"text","bbox":[1,2,3,4]}]'), "pp": pp()})
    assert page["blocks"] == before["blocks"] and page["reading_order"] == before["reading_order"]
    assert page["selected_geometry_id"] is None
    assert {c["provider"] for c in page["geometry_candidates"]} == {"monkey", "pp"}


def test_schema_copy_stays_in_sync() -> None:
    standalone = read(ROOT / "specs/geometry-candidate.schema.json")
    standalone.pop("$schema")
    standalone.pop("$id")
    assert read(ROOT / "specs/layout-ir.schema.json")["$defs"]["geometryCandidate"] == standalone


@pytest.fixture
def geometry_private() -> Iterator[Path]:
    path = PRIVATE / ("geometry-test-" + uuid.uuid4().hex)
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path)


def test_sealed_replay_writes_overlays_without_overwrite(geometry_private: Path) -> None:
    tmp_path = geometry_private
    path = tmp_path / "page.png"
    Image.new("RGB", (400, 200), "white").save(path)
    body = tmp_path / "pp.json"
    save(body, pp())
    manifest = tmp_path / "manifest.json"
    save(
        manifest,
        {
            "image": {"path": str(path), "sha256": digest(path)},
            "sources": [{"provider": "pp", "path": str(body), "sha256": digest(body)}],
            "page": {"page_index": 0, "width_pt": 200, "height_pt": 100},
            "transform": {
                "page_size_pt": [200, 100],
                "raster_size_px": [400, 200],
                "crop_px": [0, 0, 400, 200],
                "input_size_px": [400, 200],
            },
        },
    )
    out = tmp_path / "out"
    receipt = replay(manifest, out)
    assert receipt["model_calls"] == 0 and receipt["sources_unchanged"]
    assert receipt["candidate_count"] == 3 and (out / "pp-overlay.png").is_file()
    with pytest.raises(ValueError, match="OUTPUT_ALREADY_EXISTS"):
        replay(manifest, out)
    body.write_text("{}")
    with pytest.raises(ValueError, match="SEALED_INPUT_HASH_MISMATCH"):
        replay(manifest, tmp_path / "out2")
    assert not (tmp_path / "out2").exists()
