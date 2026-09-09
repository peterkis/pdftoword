"""Test real evidence redaction; no second sanitizer is implemented here."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import httpx
import pytest

from model_contract_discovery import (
    HttpClient,
    Timeouts,
    compute_json_fingerprint,
    redact_base64_images,
    redact_text,
    redact_url,
    sanitize_headers,
    scrub,
    wire_shape,
)


@pytest.mark.parametrize("port", [9000, 8000, 8080])
def test_host_query_and_credentials_redacted(port: int) -> None:
    """Only path and port survive a URL; no userinfo or query credentials."""
    url = f"http://user:synthetic-password@server.invalid:{port}/v1/models?token=private#private"
    assert redact_url(url) == f"http://MODEL_SERVER_IP:{port}/v1/models"


@pytest.mark.parametrize("header", ["Authorization", "X-API-Key", "api-key", "token", "Cookie"])
def test_headers_redacted(header: str) -> None:
    """Header matching is case insensitive and retains safe content type."""
    result = sanitize_headers({header: "synthetic-secret", "Content-Type": "application/json"})
    assert result[header] == "[REDACTED]"
    assert result["Content-Type"] == "application/json"


@pytest.mark.parametrize(
    "data",
    [
        {"image": "data:image/png;base64,xyz"},
        {"nested": ["data:image/png;base64,xyz"]},
        {"outputImages": {"page.jpg": "A" * 1200}},
        {"other": "A" * 1200},
    ],
)
def test_recursive_image_stripping(data: object) -> None:
    """Maps, lists, short data URLs and unknown long Base64 fields are stripped."""
    serialized = json.dumps(redact_base64_images(data))
    assert "data:image" not in serialized
    assert "A" * 100 not in serialized


def test_redact_text_never_previews() -> None:
    """Even short private text is represented only by a digest and length."""
    assert "private-text" not in redact_text("private-text", max_preview=100)
    assert "length=12" in redact_text("private-text")


def test_scrub_credentials_in_nested_schema_and_values() -> None:
    """Known secrets are replaced even under an unknown field."""
    data = {
        "unexpected": "prefix synthetic-secret suffix",
        "Authorization": "Bearer value",
        "servers": [{"url": "http://server.invalid"}],
        "description": "PRIVATE DOCUMENT",
        "example": "PRIVATE DOCUMENT",
    }
    result = scrub(data, ("synthetic-secret",))
    serialized = json.dumps(result)
    for private in ("synthetic-secret", "Bearer value", "server.invalid", "PRIVATE DOCUMENT"):
        assert private not in serialized


def test_shapes_preserve_unknown_fields_without_text() -> None:
    """Unknown wire fields remain discoverable while their string values are absent."""
    data = {"custom": "PRIVATE DOCUMENT", "nested": [{"unexpected": "PRIVATE DOCUMENT"}]}
    result = wire_shape(data)
    assert result["properties"]["custom"]["type"] == "string"
    assert "unexpected" in json.dumps(result)
    assert "PRIVATE DOCUMENT" not in json.dumps(result)


def test_json_fingerprint_is_canonical() -> None:
    """Dictionary order does not change canonical evidence fingerprints."""
    assert compute_json_fingerprint({"a": 1, "b": 2}) == compute_json_fingerprint({"b": 2, "a": 1})
    assert compute_json_fingerprint({"a": 1}) != compute_json_fingerprint({"a": 2})


def test_http_exception_does_not_leak() -> None:
    """HTTP error strings may contain arbitrary secrets; only the class is retained."""

    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("synthetic-secret PRIVATE DOCUMENT", request=request)

    with HttpClient(Timeouts(), httpx.MockTransport(respond)) as client:
        status, body, meta = client.get("http://127.0.0.1:9000/v1/models")
    assert status == 0
    assert body == {}
    assert meta.error == "ConnectError"
    assert "synthetic-secret" not in json.dumps(meta.to_dict())


def test_non_json_body_is_not_logged() -> None:
    """Reverse-proxy HTML errors never enter metadata or a raw text preview."""
    with HttpClient(
        Timeouts(),
        httpx.MockTransport(
            lambda _: httpx.Response(502, text="PRIVATE DOCUMENT"),
        ),
    ) as client:
        _, body, meta = client.get("http://127.0.0.1:8080/openapi.json")
    assert body == {}
    assert meta.error == "NON_JSON_RESPONSE"


def test_redirects_not_followed() -> None:
    """An OpenAPI server redirect cannot send credentials away from loopback."""
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(307, headers={"Location": "http://server.invalid"})

    with HttpClient(Timeouts(), httpx.MockTransport(respond)) as client:
        status, _, _ = client.get("http://127.0.0.1:8080/openapi.json")
    assert status == 307
    assert len(calls) == 1


@pytest.mark.parametrize(
    "path",
    [
        "tmp/model-contract-discovery/run/pp.openapi.raw.redacted.json",
        ".env.local",
        "tmp/model-contract-discovery/run/monkey.chat.raw.json",
        "scripts/test-page.jpg",
    ],
)
def test_sensitive_assets_are_ignored(path: str) -> None:
    """Ask Git to evaluate real ignore rules, including the redacted raw suffix."""
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(["git", "check-ignore", "--no-index", "--quiet", path], cwd=root)
    assert result.returncode == 0
