"""Synthetic response/geometry variation checks, not new model-quality claims."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from PIL import Image
from prototypes.docx_output.common import Json, layout, new_job, read
from prototypes.docx_output.ovis_replay import recover_ovis
from prototypes.docx_output.pipeline import finish, source_image
from prototypes.docx_output.pp_layout import apply_pp_layout


def case(
    root: Path, width: int = 600, questions: int = 2, options: int = 4, rows: int = 1
) -> tuple[Path, Json, Json, Json]:
    """Create independently sized source images and equivalent synthetic wire geometry."""
    height = round(width * 1.4)
    image_path = root / "source.png"
    with Image.new("RGB", (width, height), "white") as image:
        image.save(image_path)
    image_path.chmod(0o600)
    job = new_job(root / "jobs")
    ir = layout(job, image_path, 1)
    p = source_image(job, ir, image_path)
    paragraphs = ["# Synthetic layout"]
    regions: list[Json] = [
        {"block_label": "doc_title", "block_bbox": [150, 20, 850, 50], "block_content": "POISON"}
    ]
    fine: list[list[float]] = []
    for q in range(questions):
        y = 100 + q * 340
        paragraphs.append(f"{q + 1}. 保留原文与公式")
        regions.append(
            {"block_label": "text", "block_bbox": [80, y, 920, y + 24], "block_content": "POISON"}
        )
        fine.append([80, y, 920, y + 24])
        for n in range(options):
            paragraphs.append(f"{chr(65 + n)}. $x_{n + 1}>0$")
        regions.append(
            {
                "block_label": "text",
                "block_bbox": [110, y + 65, 920, y + 65 + (rows - 1) * 60 + 24],
                "block_content": "POISON",
            }
        )
        for row in range(rows):
            cols = options // rows
            for col in range(cols):
                left = 110 + col * 810 / cols
                fine.append([left, y + 65 + row * 60, left + 810 / cols - 30, y + 89 + row * 60])
    scale = width / 1000
    for r in regions:
        r["block_bbox"] = [v * scale for v in r["block_bbox"]]
    raw = {
        "width": width,
        "height": height,
        "parsing_res_list": regions,
        "overall_ocr_res": {
            "rec_boxes": [[v * scale for v in b] for b in fine],
            "rec_texts": ["POISON"],
        },
        "formula_res_list": [],
    }
    recover_ovis(
        job,
        ir,
        p,
        {"choices": [{"finish_reason": "stop", "message": {"content": "\n\n".join(paragraphs)}}]},
        "ovis",
    )
    return job, ir, p, {"result": {"layoutParsingResults": [{"prunedResult": raw}]}}


@pytest.mark.parametrize("width", [300, 600, 1200])
@pytest.mark.parametrize("questions", [1, 3])
@pytest.mark.parametrize("options,rows", [(2, 1), (4, 1), (4, 2)])
def test_supported_layout_variations(
    private_case: Path, width: int, questions: int, options: int, rows: int
) -> None:
    job, ir, p, pp = case(private_case, width, questions, options, rows)
    before = copy.deepcopy([b["content"] for b in p["blocks"]])
    apply_pp_layout(job, ir, p, pp, "pp")
    assert ir["metadata"]["layout_validation"]["status"] == "APPLIED"
    assert [list(map(len, g["rows"])) for g in ir["metadata"]["text_groups"]] == [
        [options // rows] * rows
    ] * questions
    assert [b["content"] for b in p["blocks"]] == before
    finish(job, ir)
    assert read(job / "qa.json")["omml_formula_count"] == questions * options
    assert read(job / "qa.json")["model_call_count"] == 0


@pytest.mark.parametrize(
    "fault",
    [
        "missing_question",
        "reordered",
        "bad_box",
        "bad_size",
        "missing_wire",
        "duplicate",
        "multicolumn",
        "rotated",
    ],
)
def test_layout_failure_preserves_ovis_output(private_case: Path, fault: str) -> None:
    job, ir, p, pp = case(private_case)
    original = copy.deepcopy(p)
    raw = pp["result"]["layoutParsingResults"][0]["prunedResult"]
    if fault == "missing_question":
        raw["parsing_res_list"] = raw["parsing_res_list"][:3]
    elif fault == "reordered":
        raw["parsing_res_list"] = list(reversed(raw["parsing_res_list"]))
    elif fault == "bad_box":
        raw["parsing_res_list"][0]["block_bbox"] = [0, 0, float("nan"), 30]
    elif fault == "bad_size":
        raw["width"] += 1
    elif fault == "duplicate":
        raw["parsing_res_list"].append(copy.deepcopy(raw["parsing_res_list"][1]))
    elif fault == "multicolumn":
        raw["parsing_res_list"] = [
            {"block_label": "text", "block_bbox": [40, 100, 270, 140]},
            {"block_label": "text", "block_bbox": [320, 100, 560, 140]},
        ]
    elif fault == "rotated":
        raw["overall_ocr_res"]["textline_orientation_angles"] = [90]
    else:
        pp = {}
    apply_pp_layout(job, ir, p, pp, "pp")
    assert ir["metadata"]["layout_validation"]["status"] == "FALLBACK"
    assert len({i["id"] for i in ir["issues"]}) == len(ir["issues"])
    assert p["blocks"] == original["blocks"]
    assert p["reading_order"] == original["reading_order"]
    assert ir["metadata"].get("layout_profile") != "pp_geometry_flow"
    finish(job, ir)
    qa = read(job / "qa.json")
    assert qa["omml_formula_count"] == 8 and qa["docx_package_valid"]
    assert qa["layout_validation"]["status"] == "FALLBACK"


def test_disabled_orientation_sentinel_is_not_rotation(private_case: Path) -> None:
    job, ir, p, pp = case(private_case)
    ocr = pp["result"]["layoutParsingResults"][0]["prunedResult"]["overall_ocr_res"]
    ocr.update(model_settings={"use_textline_orientation": False}, textline_orientation_angles=[-1])
    apply_pp_layout(job, ir, p, pp, "pp")
    assert ir["metadata"]["layout_validation"]["status"] == "APPLIED"


@pytest.mark.parametrize("failed", [None, "pp", "ovis"])
def test_live_uses_shared_reconstruction(
    private_case: Path, monkeypatch: pytest.MonkeyPatch, failed: str | None
) -> None:
    """Mock wire calls prove routing and failure containment, not live model quality."""
    from typing import Any

    import httpx
    from prototypes.docx_output.pipeline import convert
    from prototypes.docx_output.raster_bridge import recognize

    _, reference, _, pp = case(private_case)
    pp.update(logId="synthetic", errorCode=0, errorMsg="Success")
    pp["result"]["dataInfo"] = {"width": 600, "height": 840, "type": "image"}
    pp["result"]["layoutParsingResults"][0]["markdown"] = {
        "text": "POISON",
        "isStart": True,
        "isEnd": True,
    }
    seen = []

    def reply(self: httpx.Client, url: str, **kwargs: Any) -> httpx.Response:
        provider = "pp" if ":8080/" in url else "ovis"
        seen.append(provider)
        if provider == failed:
            raise httpx.ConnectError("synthetic")
        body = (
            pp
            if provider == "pp"
            else {
                "model": "ovis-ocr2",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": reference["provenance"]["ovis_content"]["0"]},
                    }
                ],
            }
        )
        return httpx.Response(200, json=body)

    monkeypatch.setattr(httpx.Client, "post", reply)
    job = convert(
        private_case / "source.png",
        mode="raster",
        output_root=private_case / "live",
        allow_model_calls=True,
        confirm_no_auth=True,
    )
    ir = read(job / "layout.auto.json")
    qa = read(job / "qa.json")
    assert seen == (["ovis"] if failed == "ovis" else ["ovis", "pp"])
    assert qa["model_call_count"] == len(seen)
    if failed == "ovis":
        assert qa["execution_status"] == "DEMO_OUTPUT_INSUFFICIENT"
        assert not ir["pages"][0]["blocks"]
    else:
        assert qa["omml_formula_count"] == 8
        assert qa["layout_validation"]["status"] == ("FALLBACK" if failed else "APPLIED"), (
            qa["layout_validation"],
            ir["issues"],
        )
        assert [b["content"] for b in ir["pages"][0]["blocks"]] == [
            b["content"] for b in reference["pages"][0]["blocks"]
        ]
    recognize(job, ir, ir["pages"][0], read(job / "request-manifest.json"), primary="ovis-pp")
    assert len(seen) == qa["model_call_count"]


def test_mixed_page_results_retained(private_case: Path) -> None:
    """A failed later page cannot erase an earlier accepted page's decision."""
    job, ir, p, pp = case(private_case)
    apply_pp_layout(job, ir, p, pp, "pp0")
    second = source_image(job, ir, private_case / "source.png", 1)
    recover_ovis(
        job,
        ir,
        second,
        {"choices": [{"finish_reason": "stop", "message": {"content": "1. 第二页保留原文"}}]},
        "ovis1",
    )
    before = copy.deepcopy(second["blocks"])
    apply_pp_layout(job, ir, second, {}, "pp1")
    assert second["blocks"] == before
    assert ir["metadata"]["layout_validation"]["status"] == "PARTIAL"
    assert ir["metadata"]["layout_by_page"]["0"]["status"] == "APPLIED"
    assert ir["metadata"]["layout_by_page"]["1"]["status"] == "FALLBACK"
    finish(job, ir)
    assert read(job / "qa.json")["omml_formula_count"] == 8
