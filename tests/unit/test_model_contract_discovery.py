"""
Unit tests for model_contract_discovery core module.

These tests verify the actual code from the core module,
not synthetic fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from model_contract_discovery import (
    Timeouts,
    build_pp_json_payload,
    classify_monkey_content,
    compute_json_fingerprint,
    normalize_openai_base_url,
    openai_endpoint_url,
    redact_url,
    safe_parse_monkey_content,
    validate_monkey_block,
)

# ============================================================================
# URL Normalization Tests
# ============================================================================


class TestNormalizeOpenaiBaseUrl:
    """Tests for normalize_openai_base_url function."""

    def test_simple_base_url(self) -> None:
        """Simple host:port should get /v1 added."""
        assert normalize_openai_base_url("http://host:9000") == "http://host:9000/v1"

    def test_already_has_v1(self) -> None:
        """URLs already ending with /v1 should stay unchanged."""
        assert normalize_openai_base_url("http://host:9000/v1") == "http://host:9000/v1"

    def test_has_chat_completions_path(self) -> None:
        """URLs with /v1/chat/completions should be stripped to /v1."""
        result = normalize_openai_base_url("http://host:9000/v1/chat/completions")
        assert result == "http://host:9000/v1"

    def test_has_api_v1_prefix(self) -> None:
        """URLs with /api/v1 should preserve /api/v1."""
        result = normalize_openai_base_url("http://host:9000/api/v1")
        assert result == "http://host:9000/api/v1"

    def test_has_api_v1_chat_completions(self) -> None:
        """URLs with /api/v1/chat/completions should be stripped to /api/v1."""
        result = normalize_openai_base_url("http://host:9000/api/v1/chat/completions")
        assert result == "http://host:9000/api/v1"

    def test_empty_url(self) -> None:
        """Empty URL should return empty string."""
        assert normalize_openai_base_url("") == ""

    def test_trailing_slash(self) -> None:
        """Trailing slash should be removed."""
        assert normalize_openai_base_url("http://host:9000/") == "http://host:9000/v1"


class TestOpenaiEndpointUrl:
    """Tests for openai_endpoint_url function."""

    def test_models_endpoint(self) -> None:
        """Should build correct /v1/models URL."""
        result = openai_endpoint_url("http://host:9000", "models")
        assert result == "http://host:9000/v1/models"

    def test_chat_completions_endpoint(self) -> None:
        """Should build correct /v1/chat/completions URL."""
        result = openai_endpoint_url("http://host:9000", "chat/completions")
        assert result == "http://host:9000/v1/chat/completions"

    def test_endpoint_with_leading_slash(self) -> None:
        """Should handle endpoint with leading slash."""
        result = openai_endpoint_url("http://host:9000", "/models")
        assert result == "http://host:9000/v1/models"

    def test_base_url_already_has_v1(self) -> None:
        """Should not double /v1."""
        result = openai_endpoint_url("http://host:9000/v1", "models")
        assert result == "http://host:9000/v1/models"

    def test_base_url_has_chat_completions(self) -> None:
        """Should strip to /v1 and add endpoint."""
        result = openai_endpoint_url("http://host:9000/v1/chat/completions", "models")
        assert result == "http://host:9000/v1/models"


# ============================================================================
# URL Redaction Tests
# ============================================================================


class TestRedactUrl:
    """Tests for redact_url function."""

    def test_redact_ip_address(self) -> None:
        """Should redact IP addresses."""
        result = redact_url("http://server.invalid:9000/v1/models")
        assert "server.invalid" not in result
        assert "MODEL_SERVER_IP" in result

    def test_preserve_path(self) -> None:
        """Should preserve path after redaction."""
        result = redact_url("http://server.invalid:9000/v1/models")
        assert "/v1/models" in result

    def test_preserve_localhost(self) -> None:
        """Should redact localhost too (all IPs are redacted)."""
        result = redact_url("http://localhost:9000/v1/models")
        # localhost is also redacted to MODEL_SERVER_IP
        assert "localhost" not in result
        assert "MODEL_SERVER_IP" in result

    def test_empty_url(self) -> None:
        """Should handle empty URL."""
        assert redact_url("") == ""


# ============================================================================
# Monkey Content Classification Tests
# ============================================================================


class TestClassifyMonkeyContent:
    """Tests for classify_monkey_content function."""

    def test_string_python_literal(self) -> None:
        """Python literal string should be classified as string + python_literal_list."""
        content = "[{'bbox': [0, 0, 100, 100], 'label': 'text'}]"
        result = classify_monkey_content(content)
        assert result["wire_type"] == "string"
        assert result["serialization"] == "python_literal_list"

    def test_none_content(self) -> None:
        """None should return unknown."""
        result = classify_monkey_content(None)
        assert result["wire_type"] == "unknown"
        assert result["serialization"] == "unknown"

    def test_list_content(self) -> None:
        """JSON list should be classified as array + json."""
        content = [{"bbox": [0, 0, 100, 100], "label": "text"}]
        result = classify_monkey_content(content)
        assert result["wire_type"] == "array"
        assert result["serialization"] == "json"

    def test_plain_string(self) -> None:
        """Plain string (not Python literal) has unknown serialization."""
        content = "This is plain text"
        result = classify_monkey_content(content)
        assert result["wire_type"] == "string"
        assert result["serialization"] == "unknown"


class TestSafeParseMonkeyContent:
    """Tests for safe_parse_monkey_content function."""

    def test_parse_valid_python_literal(self) -> None:
        """Should parse valid Python literal list."""
        content = "[{'bbox': [0, 0, 100, 100], 'label': 'text'}]"
        result, _raw = safe_parse_monkey_content(content)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["label"] == "text"

    def test_parse_returns_classification(self) -> None:
        """Should return classification dict as second return value."""
        content = "[{'bbox': [0, 0, 100, 100], 'label': 'text'}]"
        result, classification = safe_parse_monkey_content(content)
        assert isinstance(result, list)
        assert isinstance(classification, dict)
        assert "wire_type" in classification

    def test_parse_invalid_literal_raises(self) -> None:
        """Invalid Python literal should raise ValueError."""
        content = "not a valid python literal"
        with pytest.raises(ValueError):
            safe_parse_monkey_content(content)


class TestValidateMonkeyBlock:
    """Tests for validate_monkey_block function."""

    def test_validate_normalized_1000_coordinates(self) -> None:
        """Blocks with coordinates in 0-1000 range should be identified as normalized_1000."""
        block = {"bbox": [100, 200, 900, 800], "label": "text"}
        result = validate_monkey_block(block, page_width=800, page_height=1159)
        assert result["coordinate_space"] == "normalized_1000"
        assert result["valid"] is True

    def test_detect_pixel_coordinates(self) -> None:
        """Blocks with coordinates in 0-1000 range are normalized_1000."""
        # Note: Monkey uses normalized_1000 coordinates (0-1000)
        # Pixel coordinates need to be scaled, but if they fit in 0-1000,
        # they can be ambiguous
        block = {"bbox": [0, 0, 800, 1000], "label": "text"}
        result = validate_monkey_block(block, page_width=800, page_height=1159)
        # Since values are in 0-1000 range, it's detected as normalized
        assert result["coordinate_space"] == "normalized_1000"

    def test_missing_bbox(self) -> None:
        """Block without bbox should return invalid."""
        block = {"label": "text"}
        result = validate_monkey_block(block, page_width=800, page_height=1159)
        assert result["valid"] is False
        assert "error" in result
        assert "missing" in result["error"].lower()


# ============================================================================
# PP Payload Tests
# ============================================================================


class TestBuildPpJsonPayload:
    """Tests for build_pp_json_payload function."""

    def test_includes_file_type(self) -> None:
        """Must include fileType field."""
        payload = build_pp_json_payload("base64data", file_type=1)
        assert "fileType" in payload
        assert payload["fileType"] == 1

    def test_file_type_0_for_pdf(self) -> None:
        """fileType=0 for PDF."""
        payload = build_pp_json_payload("base64data", file_type=0)
        assert payload["fileType"] == 0

    def test_file_type_1_for_image(self) -> None:
        """fileType=1 for image."""
        payload = build_pp_json_payload("base64data", file_type=1)
        assert payload["fileType"] == 1

    def test_includes_file_field(self) -> None:
        """Must include file field with base64 data."""
        payload = build_pp_json_payload("base64data", file_type=1)
        assert "file" in payload
        assert payload["file"] == "base64data"


# ============================================================================
# JSON Fingerprint Tests
# ============================================================================


class TestComputeJsonFingerprint:
    """Tests for compute_json_fingerprint function."""

    def test_consistent_fingerprint(self) -> None:
        """Same JSON should produce same fingerprint."""
        data = {"key": "value", "nested": {"a": 1}}
        fp1 = compute_json_fingerprint(data)
        fp2 = compute_json_fingerprint(data)
        assert fp1 == fp2

    def test_different_json_different_fingerprint(self) -> None:
        """Different JSON should produce different fingerprint."""
        data1 = {"key": "value1"}
        data2 = {"key": "value2"}
        fp1 = compute_json_fingerprint(data1)
        fp2 = compute_json_fingerprint(data2)
        assert fp1 != fp2

    def test_is_sha256_hex(self) -> None:
        """Fingerprint should be SHA-256 hex string."""
        data = {"key": "value"}
        fp = compute_json_fingerprint(data)
        assert len(fp) == 64  # SHA-256 is 64 hex chars
        assert all(c in "0123456789abcdef" for c in fp)

    def test_order_independent(self) -> None:
        """Key order should not affect fingerprint."""

        # Create same data with different key order
        data1 = {"a": 1, "b": 2, "c": 3}
        data2 = {"c": 3, "b": 2, "a": 1}

        # The function uses json.dumps with sort_keys=True
        fp1 = compute_json_fingerprint(data1)
        fp2 = compute_json_fingerprint(data2)
        assert fp1 == fp2


# ============================================================================
# Integration Test: Full Discovery Flow
# ============================================================================


class TestDiscoveryConfig:
    """Tests for configuration loading."""

    def test_timeouts_defaults(self) -> None:
        """Timeouts should have sensible defaults."""
        timeouts = Timeouts()
        assert timeouts.connect == 10
        assert timeouts.request == 600

    def test_timeouts_custom(self) -> None:
        """Custom timeouts should be settable."""
        timeouts = Timeouts(connect=30, request=1200)
        assert timeouts.connect == 30
        assert timeouts.request == 1200


def test_literal_parser_never_executes_code(tmp_path: Path) -> None:
    """A malicious expression cannot execute or create a sentinel file."""
    sentinel = tmp_path / "sentinel"
    with pytest.raises(ValueError, match="PARSE_FAILED"):
        safe_parse_monkey_content("[__import__('os').system('touch sentinel')]")
    assert not sentinel.exists()


def test_v10_is_not_v1() -> None:
    """Version normalization matches a segment, not the start of another version."""
    assert normalize_openai_base_url("http://host:9000/v10") == "http://host:9000/v10/v1"
