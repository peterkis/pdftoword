"""Synthetic regression checks for the actual raster metrics implementation."""

import pytest

from raster_regression import bbox_error, compare_text, geometry_metrics, iou, region


def test_iou_and_invalid_boxes() -> None:
    assert iou([0, 0, 10, 10], [5, 0, 15, 10]) == pytest.approx(1 / 3)
    assert iou([0, 0, 1, 1], [1, 1, 2, 2]) == 0
    for box in ([0, 0, 0, 1], [2, 0, 1, 1], [0, 0, float("nan"), 1], [-1, 0, 1, 1]):
        assert bbox_error(box, 10, 10)


def test_one_to_one_and_merge() -> None:
    gt = [region("g1", "text", [0, 0, 10, 10]), region("g2", "text", [10, 0, 20, 10])]
    pred = [region("p1", "text", [0, 0, 20, 10])]
    result = geometry_metrics(gt, pred, 0.5)
    assert (result["tp"], result["fp"], result["fn"]) == (1, 0, 1)
    assert result["recall"] == 0.5
    assert len(result["merges"]) == 1
    assert geometry_metrics(pred, gt, 0.5)["splits"]
    assert geometry_metrics([], [], 0.5)["recall"] is None


def test_character_differences_survive_normalization() -> None:
    assert not compare_text("x<0, y", "x≤0, v")["normalized_equal"]
    assert compare_text("a b", "ab")["normalized_equal"]
    assert not compare_text("A. 2cm", "B. 3cm")["normalized_equal"]


def test_real_label_case_and_aliases_are_not_quality_errors() -> None:
    """Uppercase wire categories retain their meaning in comparison only."""
    truth = [region("g1", "visual", [0, 0, 10, 10]), region("g2", "text", [10, 0, 20, 10])]
    prediction = [
        region("p1", "Picture", [0, 0, 10, 10]),
        region("p2", "List-item", [10, 0, 20, 10]),
    ]
    assert geometry_metrics(truth, prediction, 0.75)["tp"] == 2
    assert prediction[0]["raw_label"] == "Picture"


def test_invalid_prediction_counts_and_iou_threshold_boundary() -> None:
    truth = [region("g", "text", [0, 0, 10, 10])]
    predictions = [
        region("p", "text", [0, 0, 20, 10]),
        region("bad", "text", [0, 0, 0, 0], error="NONPOSITIVE_BBOX"),
    ]
    at = geometry_metrics(truth, predictions, 0.5)
    assert (at["tp"], at["fp"], at["invalid_count"]) == (1, 1, 1)
    assert geometry_metrics(truth, predictions, 0.500001)["tp"] == 0
    assert geometry_metrics(truth, [], 0.5)["fn"] == 1


def test_synthetic_fixture_uses_actual_matching() -> None:
    from raster_regression import ROOT, read_json

    fixture = read_json(ROOT / "tests/fixtures/raster_regression/geometry.synthetic.json")
    result = geometry_metrics(fixture["ground_truth"], fixture["predictions"], 0.75)
    assert result["tp"] == fixture["expected_tp_at_075"]
