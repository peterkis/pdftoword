"""Offline preparation and provider normalization tests."""

from pathlib import Path

import pytest
from PIL import Image

from raster_regression import matrix, parse_prediction, prepare


def test_prepare_preserves_source_and_pixels(tmp_path: Path) -> None:
    source = tmp_path / "中文 source.png"
    Image.new("RGB", (32, 20), (31, 98, 144)).save(source, format="JPEG")
    original = source.read_bytes()
    manifest = prepare(source, "synthetic", tmp_path / "case")
    assert source.read_bytes() == original
    assert (tmp_path / "case/source.jpg").read_bytes() == original
    assert manifest["variants"]["jpg"]["mime"] == "image/jpeg"
    assert manifest["variants"]["jpg"]["file_sha256"] != manifest["variants"]["png"]["file_sha256"]
    assert (
        manifest["variants"]["jpg"]["decoded_pixel_sha256"]
        == manifest["variants"]["png"]["decoded_pixel_sha256"]
    )
    with pytest.raises(ValueError, match="OUTPUT_NOT_EMPTY"):
        prepare(source, "synthetic", tmp_path / "case")


@pytest.mark.parametrize("mode,orientation", [("CMYK", 1), ("RGB", 6)])
def test_comparison_conditions(tmp_path: Path, mode: str, orientation: int) -> None:
    source = tmp_path / "input.jpg"
    exif = Image.Exif()
    exif[274] = orientation
    Image.new(mode, (20, 20)).save(source, exif=exif)
    with pytest.raises(ValueError, match="SIMPLE_COMPARISON_CONDITIONS_NOT_MET"):
        prepare(source, "synthetic", tmp_path / "case")


def test_normalized_coordinates_and_null_order() -> None:
    body = {
        "model": "MonkeyOCRv2",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": "[{'label': 'image', 'bbox': [100, 200, 300, 400]}]"},
            }
        ],
    }
    pred = parse_prediction("monkey", body, 800, 1200)
    assert pred["layers"]["macro"][0]["bbox"] == [80, 240, 240, 480]
    pp = {
        "result": {
            "dataInfo": {"width": 800, "height": 1200},
            "layoutParsingResults": [
                {
                    "prunedResult": {
                        "width": 800,
                        "height": 1200,
                        "parsing_res_list": [
                            {
                                "block_label": "text",
                                "block_bbox": [1, 2, 30, 40],
                                "block_order": None,
                            }
                        ],
                    }
                }
            ],
        }
    }
    assert parse_prediction("pp", pp, 800, 1200)["layers"]["paragraph"][0]["order"] is None
    with pytest.raises(ValueError, match="COORDINATE_MAPPING_UNRESOLVED"):
        parse_prediction("pp", pp, 900, 1200)
    body["choices"][0]["finish_reason"] = "length"  # type: ignore[index]
    with pytest.raises(ValueError, match="INCOMPLETE_LENGTH"):
        parse_prediction("monkey", body, 800, 1200)


def test_matrix_is_fixed_alternating() -> None:
    rows = matrix()
    assert len(rows) == 14
    for provider, count in [("monkey", 3), ("pp", 3), ("ovis", 1)]:
        for variant in ["jpg", "png"]:
            assert (
                sum(r["provider"] == provider and r["variant_id"] == variant for r in rows) == count
            )
    assert [r["variant_id"] for r in rows[:6]] == ["jpg", "png", "png", "jpg", "jpg", "png"]


def test_icc_conditions_are_not_silently_converted(tmp_path: Path) -> None:
    source = tmp_path / "profile.jpg"
    Image.new("RGB", (20, 20)).save(source, icc_profile=b"nontrivial-profile")
    with pytest.raises(ValueError, match="SIMPLE_COMPARISON_CONDITIONS_NOT_MET"):
        prepare(source, "synthetic", tmp_path / "case")


def test_null_order_is_missing_not_geometrically_inferred() -> None:
    from raster_regression import order_metrics, region

    gt = {
        "regions": [
            region("a", "text", [0, 0, 10, 10], layer="paragraph"),
            region("b", "text", [0, 20, 10, 30], layer="paragraph"),
        ],
        "reading_order_constraints": [["a", "b"]],
    }
    pred = {
        "layers": {
            "paragraph": [
                region("p1", "text", [0, 0, 10, 10], order=0),
                region("p2", "text", [0, 20, 10, 30], order=None),
            ]
        }
    }
    assert order_metrics(gt, pred)["missing"] == 1
    assert order_metrics(gt, pred)["coverage"] == 0
