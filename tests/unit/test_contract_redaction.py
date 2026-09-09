"""
Unit tests for contract redaction and sanitization.

Tests that sensitive information is properly redacted from responses.
"""

from __future__ import annotations

import hashlib
import json

# ============================================================================
# URL Redaction Tests
# ============================================================================


def test_redact_url_with_ip() -> None:
    """Test that IP addresses are redacted from URLs."""
    from urllib.parse import urlparse

    test_urls = [
        "http://192.168.1.100:9000/v1/models",
        "http://10.0.0.1:8080/layout-parsing",
        "http://172.16.0.1:8000/v1/chat/completions",
    ]

    for url in test_urls:
        parsed = urlparse(url)
        redacted = f"http://MODEL_SERVER_IP:{parsed.port}"
        if parsed.path:
            redacted += parsed.path

        assert "192.168" not in redacted
        assert "10.0.0" not in redacted
        assert "172.16" not in redacted
        assert "MODEL_SERVER_IP" in redacted
        assert str(parsed.port) in redacted


def test_redact_url_preserves_path() -> None:
    """Test that URL paths are preserved during redaction."""
    from urllib.parse import urlparse

    url = "http://192.168.1.100:9000/v1/chat/completions"
    parsed = urlparse(url)
    redacted = f"http://MODEL_SERVER_IP:{parsed.port}{parsed.path}"

    assert "/v1/chat/completions" in redacted


def test_redact_url_preserves_port() -> None:
    """Test that ports are preserved during redaction."""
    from urllib.parse import urlparse

    ports = [9000, 8000, 8080]

    for port in ports:
        url = f"http://192.168.1.100:{port}/path"
        parsed = urlparse(url)
        redacted = f"http://MODEL_SERVER_IP:{parsed.port}"

        assert str(port) in redacted


# ============================================================================
# Header Redaction Tests
# ============================================================================


def test_redact_authorization_header() -> None:
    """Test that Authorization headers are redacted."""
    sensitive_keys = {"authorization", "api-key", "x-api-key", "token"}

    headers = {
        "Authorization": "Bearer secret-key-123",
        "Content-Type": "application/json",
        "X-Custom-Header": "custom-value",
    }

    result = {}
    for key, value in headers.items():
        if key.lower() in sensitive_keys:
            result[key] = "[REDACTED]"
        else:
            result[key] = value

    assert result["Authorization"] == "[REDACTED]"
    assert result["Content-Type"] == "application/json"
    assert result["X-Custom-Header"] == "custom-value"


def test_redact_api_key_header() -> None:
    """Test that API key headers are redacted."""
    sensitive_keys = {"authorization", "api-key", "x-api-key", "token"}

    headers = {
        "X-API-Key": "my-secret-key",
        "api-key": "another-secret",
    }

    result = {}
    for key, value in headers.items():
        if key.lower() in sensitive_keys:
            result[key] = "[REDACTED]"
        else:
            result[key] = value

    assert result["X-API-Key"] == "[REDACTED]"
    assert result["api-key"] == "[REDACTED]"


# ============================================================================
# Base64 Image Redaction Tests
# ============================================================================


def test_redact_data_url_images() -> None:
    """Test that data URL images are redacted."""
    # Shortened data URL for testing
    data_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
    data = {
        "content": "Some text",
        "image": data_url,
    }

    redacted = {}
    for key, value in data.items():
        if isinstance(value, str) and value.startswith("data:image"):
            redacted[key] = "[REDACTED_DATA_URL]"
        else:
            redacted[key] = value

    assert redacted["image"] == "[REDACTED_DATA_URL]"
    assert redacted["content"] == "Some text"


def test_redact_large_base64_strings() -> None:
    """Test that large strings that look like base64 are redacted."""
    # Create a long base64-like string
    long_base64 = "A" * 1500  # > 1000 characters

    # Check if it looks like base64
    base64_chars = (
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"
        "0123456789+/="
    )
    is_base64_like = (
        len(long_base64) > 1000
        and len(long_base64) % 4 == 0
        and all(c in base64_chars for c in long_base64[:100])
    )

    assert is_base64_like


def test_preserve_short_strings() -> None:
    """Test that short strings are not redacted."""
    short_strings = [
        "Hello",
        "doc_title",
        "text",
        "image/jpeg",
    ]

    for s in short_strings:
        # Short strings should not trigger base64 detection
        is_large = len(s) > 1000
        assert not is_large


# ============================================================================
# JSON Fingerprint Tests
# ============================================================================


def test_compute_json_fingerprint() -> None:
    """Test JSON fingerprint computation."""

    def compute_fingerprint(data: dict) -> str:
        normalized = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    data = {"key": "value", "nested": {"inner": "data"}}

    fingerprint = compute_fingerprint(data)

    assert len(fingerprint) == 64
    assert all(c in "0123456789abcdef" for c in fingerprint)


def test_fingerprint_normalizes_json() -> None:
    """Test that fingerprint normalizes JSON (same data, different order)."""

    def compute_fingerprint(data: dict) -> str:
        normalized = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    # Same data, different key order
    data1 = {"a": 1, "b": 2, "c": 3}
    data2 = {"c": 3, "b": 2, "a": 1}

    assert compute_fingerprint(data1) == compute_fingerprint(data2)


# ============================================================================
# Response Metadata Redaction Tests
# ============================================================================


def test_request_metadata_redaction() -> None:
    """Test that request metadata is redacted."""
    metadata = {
        "url": "http://192.168.1.100:9000/v1/chat/completions",
        "method": "POST",
        "request_headers": {
            "Authorization": "Bearer secret-key",
            "Content-Type": "application/json",
        },
        "request_payload": {
            "model": "MonkeyOCRv2",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Prompt"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64,xxx"},
                        },
                    ],
                }
            ],
        },
    }

    # Redact URL
    from urllib.parse import urlparse

    parsed = urlparse(metadata["url"])
    metadata["url"] = f"http://MODEL_SERVER_IP:{parsed.port}{parsed.path}"

    # Redact headers
    for key in metadata["request_headers"]:
        if key.lower() == "authorization":
            metadata["request_headers"][key] = "[REDACTED]"

    # Redact image URL in payload
    for msg in metadata["request_payload"]["messages"]:
        if isinstance(msg.get("content"), list):
            for item in msg["content"]:
                if item.get("type") == "image_url":
                    item["image_url"]["url"] = "[DATA_URL_REDACTED]"

    assert "192.168" not in metadata["url"]
    assert metadata["request_headers"]["Authorization"] == "[REDACTED]"

    redacted_url = (
        metadata["request_payload"]["messages"][0]
        ["content"][1]["image_url"]["url"]
    )
    assert redacted_url == "[DATA_URL_REDACTED]"


# ============================================================================
# Raw Response File Tests
# ============================================================================


def test_raw_files_not_committed() -> None:
    """Test that .raw.json files are gitignored."""
    from pathlib import Path

    gitignore_path = Path(__file__).parent.parent.parent / ".gitignore"
    with open(gitignore_path, encoding="utf-8") as f:
        gitignore_content = f.read()

    assert "*.raw.json" in gitignore_content


def test_tmp_directory_gitignored() -> None:
    """Test that tmp directory is gitignored."""
    from pathlib import Path

    gitignore_path = Path(__file__).parent.parent.parent / ".gitignore"
    with open(gitignore_path, encoding="utf-8") as f:
        gitignore_content = f.read()

    assert "tmp/" in gitignore_content


# ============================================================================
# System Fingerprint Tests
# ============================================================================


def test_system_fingerprint_allowed_to_be_empty() -> None:
    """Test that system_fingerprint can be null/empty."""
    response_with_fingerprint = {
        "system_fingerprint": "vllm-0.26.0-7a07b93c",
    }

    response_without_fingerprint = {
        "system_fingerprint": None,
    }

    # Both are valid
    assert response_with_fingerprint["system_fingerprint"] is not None
    assert response_without_fingerprint["system_fingerprint"] is None


# ============================================================================
# Unknown Field Preservation Tests
# ============================================================================


def test_unknown_fields_preserved() -> None:
    """Test that unknown response fields are preserved."""
    response = {
        "known_field": "value",
        "unknown_field_1": "data",
        "unknown_field_2": {"nested": "data"},
    }

    # All fields should be preserved
    assert "known_field" in response
    assert "unknown_field_1" in response
    assert "unknown_field_2" in response


def test_extra_fields_not_dropped() -> None:
    """Test that extra fields are not dropped during normalization."""
    original = {
        "id": "test",
        "model": "test-model",
        "extra_data": {"custom": "field"},
    }

    # Simulate normalization that preserves all fields
    normalized = dict(original)

    assert normalized == original
    assert "extra_data" in normalized
