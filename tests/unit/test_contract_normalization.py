"""Observed contracts are normalized by real core functions; examples are not evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from model_contract_discovery import (
    RequestMetadata,
    build_pp_error_probes,
    build_pp_json_payload,
    error_observation,
    observe_chat,
    pp_success,
    wire_shape,
)


def chat(content: Any, model: str = "MonkeyOCRv2", finish: str = "stop") -> dict[str, Any]:
    """Synthetic chat envelope used to exercise normalization failures and success."""
    return {
        "object": "chat.completion",
        "model": model,
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
        "usage": {"total_tokens": 5},
        "system_fingerprint": None,
    }


def test_monkey_wire_string_is_preserved() -> None:
    """Parsed arrays are never misrepresented as wire arrays or pixel coordinates."""
    result = observe_chat(chat("[{'bbox': [0, 0, 900, 950], 'label': 'text'}]"), "monkey")
    wire = result["wire_contract"]
    assert wire["wire_type"] == "string"
    assert wire["serialization"] == "python_literal_list"
    assert wire["strict_json"] is False
    assert wire["parsed_type"] == "array<object>"
    assert wire["safe_parser"] == "ast.literal_eval"
    assert wire["coordinate_space"] == "normalized_1000"
    assert wire["parsed_block_count"] == 1
    assert result["system_fingerprint"] is None


@pytest.mark.parametrize(
    "content",
    [
        [{"bbox": [0, 0, 900, 950], "label": "text"}],
        '[{"bbox": [0, 0, 900, 950], "label": "text"}]',
        "[{'bbox': [0, 0, 900, 1500], 'label': 'text'}]",
        "[]",
        "PRIVATE OCR TEXT",
        None,
    ],
)
def test_invalid_monkey_contract_does_not_verify(content: Any) -> None:
    """Wrong wire type, serialization, units/range and empty output are blocked."""
    with pytest.raises(ValueError):
        observe_chat(chat(content), "monkey")


def test_ovis_markdown_metadata_without_body() -> None:
    """Ovis is treated as Markdown, not routed through the Monkey literal parser."""
    result = observe_chat(chat("# PRIVATE OCR TEXT", "ovis-ocr2"), "ovis")
    assert result["wire_contract"]["serialization"] == "markdown"
    assert result["wire_contract"]["wire_type"] == "string"
    assert len(result["wire_contract"]["content_sha256"]) == 64
    assert "PRIVATE OCR TEXT" not in json.dumps(result)


@pytest.mark.parametrize("content", [None, [], "", "   "])
def test_invalid_ovis_contract(content: Any) -> None:
    """Empty or non-string Ovis content cannot be verified."""
    with pytest.raises(ValueError):
        observe_chat(chat(content, "ovis-ocr2"), "ovis")


@pytest.mark.parametrize("finish", ["length", None, "error"])
def test_incomplete_finish_reason(finish: Any) -> None:
    """Truncated responses do not count as successful contract evidence."""
    with pytest.raises(ValueError):
        observe_chat(chat("# Text", "ovis-ocr2", finish), "ovis")


def test_pp_success_predicate() -> None:
    """PP must have both application success and a nonempty layout result list."""
    assert pp_success(200, {"errorCode": 0, "result": {"layoutParsingResults": [{}]}})
    assert not pp_success(200, {"errorCode": 9, "result": {"layoutParsingResults": [{}]}})
    assert not pp_success(200, {"errorCode": 0, "result": {}})
    assert not pp_success(200, {"errorCode": 0, "result": {"layoutParsingResults": []}})
    assert not pp_success(500, {"errorCode": 0, "result": {"layoutParsingResults": [{}]}})


@pytest.mark.parametrize("code", [1002, 422, None])
def test_http_and_application_codes_independent(code: int | None) -> None:
    """Validation must retain an observed body code, including absence."""
    meta = RequestMetadata(
        "test-request",
        "test-time",
        response_content_type="application/json",
        response_fingerprint="a" * 64,
    )
    result = error_observation(422, {"errorCode": code, "errorMsg": []}, meta)
    assert result["http_status"] == 422
    assert result["application_error_code"] == code
    assert result["error_msg_wire_type"] == "array"


def test_error_probes_preserve_valid_full_image() -> None:
    """Invalid fileType does not accidentally truncate the unrelated file field."""
    image = "synthetic-complete-image"
    probes = build_pp_error_probes(image)
    assert [probe["name"] for probe in probes] == [
        "missing_file",
        "invalid_file_type",
        "invalid_file",
    ]
    assert "file" not in probes[0]["payload"]
    assert probes[1]["payload"] == {"file": image, "fileType": 99}
    assert probes[2]["payload"]["fileType"] == 1
    assert build_pp_json_payload(image) == {"file": image, "fileType": 1}


def test_unknown_shape_fields_preserved() -> None:
    """New wire fields remain visible for contract review without their values."""
    result = wire_shape({"new_field": {"nested": "PRIVATE OCR TEXT"}})
    assert result["properties"]["new_field"]["properties"]["nested"]["type"] == "string"


def test_fixture_metadata_is_honest() -> None:
    """Synthetic examples must never carry a verified observed-evidence label."""
    fixtures = Path(__file__).resolve().parents[1] / "fixtures/model_contracts"
    for path in fixtures.glob("*.json"):
        data = json.loads(path.read_text())
        assert data["fixture_kind"] in {"synthetic_example", "sanitized_observed_wire"}
        if data["fixture_kind"] == "synthetic_example":
            assert data["contract_status"] != "verified"
        else:
            for key in (
                "source_run_id",
                "source_response_fingerprint",
                "generated_by",
                "generated_at",
                "input_file_sha256",
                "access_mode",
            ):
                assert data[key]
            assert data["access_mode"] == "frp_stcp_loopback"


def test_observed_artifacts_share_live_provenance() -> None:
    """Committed artifacts must reference actual requests from the same accepted live run."""
    from model_contract_discovery import compute_json_fingerprint

    root = Path(__file__).resolve().parents[2]
    spec = json.loads((root / "specs/discovered-model-contracts.json").read_text())
    assert spec["execution_mode"] == "live"
    assert spec["overall_status"] == "ACCEPTED"
    fingerprints = {request["response_fingerprint"] for request in spec["requests"]}
    names = [
        "monkey.models.observed.json",
        "monkey.chat.observed.json",
        "ovis.models.observed.json",
        "ovis.chat.observed.json",
        "pp.openapi.normalized.json",
        "pp.success.observed.pruned.json",
        "pp.errors.observed.json",
        "run.provenance.json",
    ]
    for name in names:
        value = json.loads((root / "tests/fixtures/model_contracts" / name).read_text())
        assert value["fixture_kind"] == "sanitized_observed_wire"
        assert value["source_run_id"] == spec["run_id"]
        assert value["input_file_sha256"] == spec["input_file_sha256"]
        sources = value["source_response_fingerprints"]
        assert set(sources).issubset(fingerprints)
        assert value["source_response_fingerprint"] == (
            sources[0] if len(sources) == 1 else compute_json_fingerprint(sources)
        )
    services = spec["services"]
    assert services["monkey"]["wire_contract"]["wire_type"] == "string"
    assert services["monkey"]["wire_contract"]["coordinate_space"] == "normalized_1000"
    assert services["ovis"]["model_id"] == "ovis-ocr2"
    assert services["paddle"]["contract_status"] in {
        "verified_from_openapi",
        "verified_runtime_without_openapi",
    }
