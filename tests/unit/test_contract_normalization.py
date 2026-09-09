"""
Unit tests for model contract normalization.

These tests verify the contract normalization logic without making network calls.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ============================================================================
# Test fixtures paths
# ============================================================================

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "model_contracts"


# ============================================================================
# OpenAI /v1/models Response Tests
# ============================================================================


def test_monkey_models_response_structure() -> None:
    """Test that MonkeyOCRv2 models response has expected structure."""
    fixture_path = FIXTURES_DIR / "monkey.models.normalized.json"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["contract_status"] == "verified"
    assert data["model_id"] == "MonkeyOCRv2"

    response = data["response"]
    assert response["object"] == "list"
    assert "data" in response
    assert isinstance(response["data"], list)

    # Check model structure
    model = response["data"][0]
    assert model["id"] == "MonkeyOCRv2"
    assert model["object"] == "model"


def test_ovis_models_response_structure() -> None:
    """Test that OvisOCR2 models response has expected structure."""
    fixture_path = FIXTURES_DIR / "ovis.models.normalized.json"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["contract_status"] == "verified"
    assert data["model_id"] == "ovis-ocr2"

    response = data["response"]
    assert response["object"] == "list"
    assert "data" in response

    model = response["data"][0]
    assert model["id"] == "ovis-ocr2"


def test_model_id_mismatch_detection() -> None:
    """Test that model ID mismatch can be detected."""
    expected_model = "MonkeyOCRv2"

    # Simulate response with wrong model
    response = {
        "object": "list",
        "data": [{"id": "OtherModel", "object": "model"}],
    }

    model_ids = [m["id"] for m in response["data"]]
    assert expected_model not in model_ids
    assert "OtherModel" in model_ids


# ============================================================================
# OpenAI Chat Completions Response Tests
# ============================================================================


def test_monkey_chat_response_structure() -> None:
    """Test that MonkeyOCRv2 chat response has expected structure."""
    fixture_path = FIXTURES_DIR / "monkey.chat.schema.json"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    response = data["response"]

    # Standard OpenAI fields
    assert "id" in response
    assert response["object"] == "chat.completion"
    assert "model" in response
    assert "choices" in response
    assert "usage" in response
    assert "system_fingerprint" in response

    # Check choices structure
    choices = response["choices"]
    assert len(choices) > 0
    assert choices[0]["finish_reason"] == "stop"

    message = choices[0]["message"]
    assert message["role"] == "assistant"

    # Monkey-specific: content is list of objects
    content = message["content"]
    assert isinstance(content, list)
    assert all("bbox" in item for item in content)
    assert all("label" in item for item in content)


def test_ovis_chat_response_structure() -> None:
    """Test that OvisOCR2 chat response has expected structure."""
    fixture_path = FIXTURES_DIR / "ovis.chat.schema.json"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    response = data["response"]

    # Standard OpenAI fields
    assert response["object"] == "chat.completion"
    assert "choices" in response
    assert "usage" in response

    # Ovis-specific: content is markdown
    content = response["choices"][0]["message"]["content"]
    assert isinstance(content, str)
    # Markdown typically starts with # for headers
    assert content.strip().startswith("#")


# ============================================================================
# PP-StructureV3 Response Tests
# ============================================================================


def test_pp_success_response_structure() -> None:
    """Test that PP-StructureV3 success response has expected structure."""
    fixture_path = FIXTURES_DIR / "pp.success.pruned.json"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["contract_status"] == "verified"
    assert data["endpoint"] == "/layout-parsing"
    assert data["method"] == "POST"
    assert data["transport"] == "json_base64"

    response = data["response"]

    # Top-level fields
    assert "logId" in response
    assert "result" in response
    assert "errorCode" in response
    assert "errorMsg" in response

    # Success indicators
    assert response["errorCode"] == 0
    assert response["errorMsg"] == "Success"

    # Result structure
    result = response["result"]
    assert "layoutParsingResults" in result
    assert "dataInfo" in result

    # Layout parsing results
    layout_results = result["layoutParsingResults"]
    assert len(layout_results) > 0

    first_page = layout_results[0]
    assert "prunedResult" in first_page

    # Block structure
    pruned_result = first_page["prunedResult"]
    assert "parsing_res_list" in pruned_result

    blocks = pruned_result["parsing_res_list"]
    assert len(blocks) > 0

    # Each block has required fields
    for block in blocks:
        assert "block_label" in block
        assert "block_content" in block
        assert "block_bbox" in block
        assert "block_id" in block
        assert "block_order" in block

        # bbox format: [x0, y0, x1, y1]
        bbox = block["block_bbox"]
        assert len(bbox) == 4
        assert all(isinstance(v, int) for v in bbox)


def test_pp_error_response_structure() -> None:
    """Test that PP-StructureV3 error responses have expected structure."""
    fixture_path = FIXTURES_DIR / "pp.error.normalized.json"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    errors = data["error_responses"]

    # Test missing file error
    missing_file = errors["missing_file"]
    assert missing_file["status_code"] == 422
    assert missing_file["response"]["errorCode"] == 422
    assert "errorMsg" in missing_file["response"]

    # Test invalid file type error
    invalid_type = errors["invalid_file_type"]
    assert invalid_type["status_code"] == 422
    assert invalid_type["response"]["errorCode"] == 422

    # Test invalid file error
    invalid_file = errors["invalid_file"]
    assert invalid_file["status_code"] == 422


def test_pp_openapi_not_available() -> None:
    """Test that PP OpenAPI unavailability is documented."""
    fixture_path = FIXTURES_DIR / "pp.openapi.status.json"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["openapi_available"] is False
    assert data["contract_status"] == "verified"


# ============================================================================
# JSON Schema Validation Tests
# ============================================================================


def test_monkey_models_json_schema() -> None:
    """Test MonkeyOCRv2 models response against JSON schema."""
    fixture_path = FIXTURES_DIR / "monkey.models.normalized.json"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    response = data["response"]

    # Required fields
    assert "object" in response
    assert "data" in response

    # data must be array
    assert isinstance(response["data"], list)

    # Each model must have id and object
    for model in response["data"]:
        assert "id" in model
        assert "object" in model


def test_pp_request_schema() -> None:
    """Test PP-StructureV3 request schema validation."""
    # Valid request
    valid_request = {
        "file": "base64_encoded_string",
        "fileType": 1,
    }

    assert "file" in valid_request
    assert "fileType" in valid_request
    assert valid_request["fileType"] in [0, 1]

    # Invalid fileType
    invalid_request = {
        "file": "base64_encoded_string",
        "fileType": 99,
    }
    assert invalid_request["fileType"] not in [0, 1]


# ============================================================================
# Fixture Integrity Tests
# ============================================================================


def test_all_fixtures_exist() -> None:
    """Test that all required fixture files exist."""
    required_fixtures = [
        "monkey.models.normalized.json",
        "monkey.chat.schema.json",
        "ovis.models.normalized.json",
        "ovis.chat.schema.json",
        "pp.openapi.status.json",
        "pp.success.pruned.json",
        "pp.error.normalized.json",
    ]

    for fixture_name in required_fixtures:
        fixture_path = FIXTURES_DIR / fixture_name
        assert fixture_path.exists(), f"Missing fixture: {fixture_name}"


def test_fixtures_are_valid_json() -> None:
    """Test that all fixture files are valid JSON."""
    fixture_files = list(FIXTURES_DIR.glob("*.json"))

    for fixture_path in fixture_files:
        with open(fixture_path, encoding="utf-8") as f:
            try:
                json.load(f)
            except json.JSONDecodeError as e:
                pytest.fail(f"Invalid JSON in {fixture_path.name}: {e}")


def test_fixtures_have_required_metadata() -> None:
    """Test that fixtures have required metadata fields."""
    fixture_files = list(FIXTURES_DIR.glob("*.json"))

    for fixture_path in fixture_files:
        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)

        assert "description" in data, f"Missing description in {fixture_path.name}"
        assert "contract_status" in data, f"Missing contract_status in {fixture_path.name}"
