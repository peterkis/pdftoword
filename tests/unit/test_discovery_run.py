"""Offline end-to-end tests of the single T0015 discovery implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from model_contract_discovery import (
    DiscoveryConfig,
    HttpClient,
    ModelConfig,
    Timeouts,
    run_discovery,
)


def pp_spec(transport: str = "application/json") -> dict[str, Any]:
    """Small documented PP endpoint with local refs and a non-runtime server."""
    return {
        "openapi": "3.1.0",
        "info": {"title": "PP synthetic API", "version": "test-only"},
        "servers": [{"url": "http://server.invalid"}],
        "paths": {
            "/layout-parsing": {
                "post": {
                    "operationId": "layout_parse",
                    "requestBody": {
                        "required": True,
                        "content": {
                            transport: {"schema": {"$ref": "#/components/schemas/Input"}},
                        },
                    },
                    "responses": {
                        "200": {"description": "success"},
                        "422": {"description": "invalid"},
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "Input": {
                    "type": "object",
                    "required": ["file", "fileType"],
                    "properties": {
                        "file": {"type": "string", "format": "binary"},
                        "fileType": {"type": "integer", "enum": [0, 1]},
                    },
                }
            }
        },
    }


def config() -> DiscoveryConfig:
    """Only loopback roots and synthetic credentials are used by mocks."""
    return DiscoveryConfig(
        monkey=ModelConfig("http://127.0.0.1:9000", "MonkeyOCRv2", "synthetic-key"),
        ovis=ModelConfig("http://127.0.0.1:8000", "ovis-ocr2", "synthetic-key"),
        pp=ModelConfig("http://127.0.0.1:8080", api_key="synthetic-key"),
    )


def handler(
    requests: list[httpx.Request],
    *,
    wrong_ovis: bool = False,
    openapi: bool = True,
    multipart: bool = False,
    diverge: bool = False,
) -> Any:
    """Return an HTTP server double, with independently controlled failures."""

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "127.0.0.1"
        port = request.url.port
        if request.url.path == "/v1/models":
            model = "MonkeyOCRv2" if port == 9000 else "ovis-ocr2"
            if wrong_ovis and port == 8000:
                model = "different-model"
            return httpx.Response(200, json={"object": "list", "data": [{"id": model}]})
        if request.url.path == "/openapi.json":
            if port != 8080 or not openapi:
                return httpx.Response(404, json={"detail": "absent"})
            media = "multipart/form-data" if multipart else "application/json"
            return httpx.Response(200, json=pp_spec(media))
        if request.url.path == "/v1/chat/completions":
            payload = json.loads(request.content)
            if payload["model"] == "t0015-invalid-model":
                return httpx.Response(404, json={"error": {"message": "not found"}})
            content = (
                "[{'bbox': [1, 2, 900, 950], 'label': 'text'}]"
                if port == 9000
                else "# PRIVATE OCR TEXT"
            )
            return httpx.Response(
                200,
                json={
                    "object": "chat.completion",
                    "model": payload["model"],
                    "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 12},
                    "system_fingerprint": None,
                },
            )
        if port == 8080:
            is_multipart = request.headers.get("content-type", "").startswith("multipart/")
            if request.url.path != "/layout-parsing" or is_multipart != multipart:
                return httpx.Response(404, json={"errorCode": 1001, "errorMsg": "absent"})
            payload = {} if is_multipart else json.loads(request.content)
            invalid = not is_multipart and (
                "file" not in payload
                or payload.get("fileType") == 99
                or payload.get("file") == "not-valid-base64!!!"
            )
            if is_multipart:
                invalid = (
                    b'name="file";' not in request.content
                    or b"\r\n99\r\n" in request.content
                    or b"not-valid-base64!!!" in request.content
                )
            if invalid:
                return httpx.Response(422, json={"errorCode": 1002, "errorMsg": "private error"})
            if diverge:
                return httpx.Response(422, json={"errorCode": 1003, "errorMsg": "divergence"})
            return httpx.Response(
                200,
                json={
                    "errorCode": 0,
                    "errorMsg": "Success",
                    "result": {
                        "layoutParsingResults": [
                            {
                                "prunedResult": {
                                    "parsing_res_list": [{"block_content": "PRIVATE OCR TEXT"}],
                                },
                                "markdown": {
                                    "text": "PRIVATE OCR TEXT",
                                    "images": {"x": "A" * 1200},
                                },
                            }
                        ],
                    },
                },
            )
        raise AssertionError("Unexpected mock request")

    return respond


def run_mock(tmp_path: Path, **options: Any) -> tuple[dict[str, Any], list[httpx.Request]]:
    """Run the real orchestration with a MockTransport and private local input."""
    image = tmp_path / "source.jpg"
    image.write_bytes(b"\xff\xd8\xff" + b"synthetic-image")
    requests: list[httpx.Request] = []
    result = run_discovery(
        config(),
        tmp_path / "run",
        image,
        transport=httpx.MockTransport(handler(requests, **options)),
        repository_root=tmp_path,
    )
    return result, requests


def test_complete_run_writes_status_and_provenance(tmp_path: Path) -> None:
    """The saved status, metadata and response references share one run identity."""
    result, requests = run_mock(tmp_path)
    assert result["overall_status"] == "ACCEPTED"
    saved = json.loads((tmp_path / "run/discovered-model-contracts.json").read_text())
    assert saved == result
    assert result["execution_mode"] == "mock"
    assert result["access_mode"] == "frp_stcp_loopback"
    assert len(result["requests"]) == len(requests)
    assert [r.url.path for r in requests[:2]] == ["/v1/models", "/v1/models"]
    for metadata in result["requests"]:
        assert len(metadata["response_fingerprint"]) == 64
        assert metadata["duration_ms"] >= 0
        assert metadata["response_content_type"] == "application/json"
    assert "PRIVATE OCR TEXT" not in json.dumps(result)


def test_model_identity_failure_stops_inference(tmp_path: Path) -> None:
    """Ovis identity mismatch must stop before all POST requests."""
    result, requests = run_mock(tmp_path, wrong_ovis=True)
    assert result["overall_status"] == "BLOCKED_MODEL_IDENTITY_MISMATCH"
    assert not any(r.method == "POST" for r in requests)


def test_openapi_priority_no_undocumented_scan(tmp_path: Path) -> None:
    """A complete OpenAPI uses documented candidates without a Cartesian expansion."""
    result, requests = run_mock(tmp_path)
    pp = result["services"]["paddle"]
    assert pp["contract_status"] == "verified_from_openapi"
    assert pp["endpoint_path"] == "/layout-parsing"
    assert pp["contract_source"] == "openapi_with_runtime_verification"
    assert not any(r.url.path == "/PP-StructureV3" for r in requests)
    assert pp["error_probes"][0]["http_status"] == 422
    assert pp["error_probes"][0]["application_error_code"] == 1002


def test_bounded_fallback(tmp_path: Path) -> None:
    """Missing OpenAPI probes exactly the configured two-by-two bounded matrix."""
    result, _ = run_mock(tmp_path, openapi=False)
    pp = result["services"]["paddle"]
    assert pp["contract_status"] == "verified_runtime_without_openapi"
    assert len(pp["probe_matrix"]) == 4
    assert {p["path"] for p in pp["probe_matrix"]} == {"/layout-parsing", "/PP-StructureV3"}


def test_multipart_uses_documented_fields(tmp_path: Path) -> None:
    """Multipart forms use documented fields and still perform three error probes."""
    result, requests = run_mock(tmp_path, multipart=True)
    assert result["overall_status"] == "ACCEPTED"
    assert result["services"]["paddle"]["transport"] == "multipart"
    uploads = [r for r in requests if r.url.path == "/layout-parsing"]
    assert len(uploads) == 4
    assert b'name="fileType"' in uploads[0].content
    assert b"\r\n1\r\n" in uploads[0].content


def test_runtime_divergence_cannot_pass(tmp_path: Path) -> None:
    """A documented endpoint rejecting its schema must not silently fall back."""
    result, _ = run_mock(tmp_path, diverge=True)
    assert result["overall_status"] == "CONTRACT_RUNTIME_DIVERGENCE"


def test_empty_json_is_sent_as_json() -> None:
    """An empty payload is a real JSON request, not an absent body."""
    seen: list[bytes] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.content)
        assert request.headers["content-type"] == "application/json"
        return httpx.Response(422, json={"errorCode": 900})

    with HttpClient(Timeouts(), transport=httpx.MockTransport(respond)) as client:
        _, _, metadata = client.post("http://127.0.0.1:8080/layout-parsing", json_data={})
    assert seen == [b"{}"]
    assert metadata.response_fingerprint


def test_real_run_requires_rotation_confirmation(tmp_path: Path) -> None:
    """The live path fails locally without operator attestation before networking."""
    image = tmp_path / "source.jpg"
    image.write_bytes(b"\xff\xd8\xff")
    with pytest.raises(ValueError, match="KEY_ROTATION"):
        run_discovery(config(), tmp_path / "run", image, repository_root=tmp_path)


def test_promotion_generates_one_correlated_artifact_set(tmp_path: Path) -> None:
    """All fixtures come from the run; a mock can only generate synthetic examples."""
    from model_contract_discovery import promote_sanitized_artifacts

    result, _ = run_mock(tmp_path)
    promoted = promote_sanitized_artifacts(
        tmp_path / "run", tmp_path / "specs", tmp_path / "fixtures"
    )
    assert len(promoted["fixtures"]) == 8
    source_fingerprints = {r["response_fingerprint"] for r in result["requests"]}
    for name in promoted["fixtures"]:
        value = json.loads((tmp_path / "fixtures" / name).read_text())
        assert value["source_run_id"] == result["run_id"]
        assert value["fixture_kind"] == "synthetic_example"
        assert value["contract_status"] != "verified"
        assert value["input_file_sha256"] == result["input_file_sha256"]
        assert set(value["source_response_fingerprints"]).issubset(source_fingerprints)
        assert "PRIVATE OCR TEXT" not in json.dumps(value)
        assert "synthetic-key" not in json.dumps(value)
    spec = json.loads((tmp_path / "specs/discovered-model-contracts.json").read_text())
    assert spec["overall_status"] == "SIMULATED_ACCEPTED"


def test_promotion_rejects_missing_evidence(tmp_path: Path) -> None:
    """An ACCEPTED status alone cannot promote an incomplete local evidence set."""
    from model_contract_discovery import promote_sanitized_artifacts

    run_mock(tmp_path)
    next((tmp_path / "run").glob("*.raw.redacted.json")).unlink()
    with pytest.raises(ValueError, match="INCOMPLETE"):
        promote_sanitized_artifacts(tmp_path / "run", tmp_path / "specs", tmp_path / "fixtures")
    assert not (tmp_path / "specs").exists()


def test_promotion_rejects_tampered_response(tmp_path: Path) -> None:
    """Redacted evidence has its own digest checked before any public writes."""
    from model_contract_discovery import promote_sanitized_artifacts

    run_mock(tmp_path)
    path = next((tmp_path / "run").glob("*.raw.redacted.json"))
    data = json.loads(path.read_text())
    data["response"] = {}
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="DIGEST_MISMATCH"):
        promote_sanitized_artifacts(tmp_path / "run", tmp_path / "specs", tmp_path / "fixtures")


def test_promotion_rejects_blocked_run(tmp_path: Path) -> None:
    """No fixture changes are made for identity or contract failure."""
    from model_contract_discovery import promote_sanitized_artifacts

    run_mock(tmp_path, wrong_ovis=True)
    with pytest.raises(ValueError, match="ACCEPTED"):
        promote_sanitized_artifacts(tmp_path / "run", tmp_path / "specs", tmp_path / "fixtures")


def test_cli_calls_core_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI only forwards config/arguments and emits a body-free summary."""
    import discover_model_contracts as cli

    calls: list[dict[str, Any]] = []

    def fake_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        assert args[1] == tmp_path / "run"
        assert args[2] == tmp_path / "private.jpg"
        assert args[3] is True
        return {
            "run_id": "mock-run",
            "overall_status": "ACCEPTED",
            "services": {"monkey": {"contract_status": "verified"}},
        }

    monkeypatch.setattr(cli, "load_config", config)
    monkeypatch.setattr(cli, "run_discovery", fake_run)
    assert (
        cli.main(
            [
                "--test-image",
                str(tmp_path / "private.jpg"),
                "--output-dir",
                str(tmp_path / "run"),
                "--promote-artifacts",
                "--confirm-no-auth",
            ]
        )
        == 0
    )
    assert len(calls) == 1
    assert calls[0]["confirmed_no_auth"] is True
    assert str(tmp_path) not in capsys.readouterr().out


def test_reusing_run_directory_is_rejected(tmp_path: Path) -> None:
    """A rerun never overwrites the input evidence behind an earlier fingerprint."""
    run_mock(tmp_path)
    with pytest.raises(ValueError, match="ALREADY_CONTAINS"):
        run_mock(tmp_path)


def test_mock_transport_cannot_follow_remote_base() -> None:
    """Runtime destinations are restricted before even an injected transport runs."""
    with (
        HttpClient(Timeouts(), httpx.MockTransport(lambda _: httpx.Response(200))) as client,
        pytest.raises(ValueError, match="NON_LOOPBACK"),
    ):
        client.get("http://server.invalid:9000/v1/models")


@pytest.mark.parametrize("failure", ["connection", "http_503", "invalid_json"])
def test_unavailable_models_are_not_identity_mismatch(tmp_path: Path, failure: str) -> None:
    """Transport/HTTP failures have no identity evidence and cannot be labelled a mismatch."""
    requests: list[httpx.Request] = []

    def unavailable(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if failure == "connection":
            raise httpx.ConnectError("not listening", request=request)
        if failure == "invalid_json":
            return httpx.Response(200, text="not JSON")
        return httpx.Response(503, json={"error": "unavailable"})

    image = tmp_path / "source.jpg"
    image.write_bytes(b"\xff\xd8\xff" + b"synthetic-image")
    result = run_discovery(
        config(),
        tmp_path / "run",
        image,
        transport=httpx.MockTransport(unavailable),
        repository_root=tmp_path,
    )
    assert result["overall_status"] == "BLOCKED_MODELS_ENDPOINT_UNAVAILABLE"
    assert all(
        service["contract_status"] == "BLOCKED_MODELS_ENDPOINT_UNAVAILABLE"
        for service in result["services"].values()
    )
    assert all(request.method == "GET" for request in requests)


def test_monkey_minimal_request_leaves_context_for_image(tmp_path: Path) -> None:
    """Contract probing must not allocate the entire server context to output tokens."""
    result, requests = run_mock(tmp_path)
    request = next(
        r for r in requests if r.url.port == 9000 and r.url.path == "/v1/chat/completions"
    )
    payload = json.loads(request.content)
    assert payload["max_tokens"] == 2048
    assert result["services"]["monkey"]["request_parameters"]["max_tokens"] == 2048
