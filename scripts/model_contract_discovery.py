"""
Model Contract Discovery - Core Module

This module provides the core logic for discovering model service contracts.
It is designed to be testable and importable, separating concerns from CLI.

Key Features:
- Proper environment variable handling (aligned with .env.example)
- Correct URL parsing (no string replace)
- Proper HTTP timeout configuration
- Monkey wire contract as string (Python literal)
- Bounded PP runtime probe when OpenAPI unavailable
- Run metadata tracking
- Artifact promotion with provenance
"""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
from jsonschema import Draft202012Validator, ValidationError
from referencing.exceptions import Unresolvable

# ============================================================================
# Configuration
# ============================================================================


@dataclass
class ModelConfig:
    """Configuration for a model service."""

    base_url: str
    model: str = ""
    api_key: str = field(default="", repr=False)


@dataclass
class Timeouts:
    """Timeout configuration."""

    connect: int = 10
    request: int = 600


@dataclass
class DiscoveryConfig:
    """Complete discovery configuration."""

    monkey: ModelConfig = field(default_factory=lambda: ModelConfig(base_url=""))
    ovis: ModelConfig = field(default_factory=lambda: ModelConfig(base_url=""))
    pp: ModelConfig = field(default_factory=lambda: ModelConfig(base_url=""))
    timeouts: Timeouts = field(default_factory=Timeouts)

    # PP candidate paths and transports for bounded probe
    # ADR-007 fallback only; OpenAPI candidates take precedence.
    pp_candidate_paths: list[str] = field(
        default_factory=lambda: ["/layout-parsing", "/PP-StructureV3"]
    )
    # Keep fallback requests bounded and serial.
    pp_candidate_transports: list[str] = field(default_factory=lambda: ["json_base64", "multipart"])


def load_config() -> DiscoveryConfig:
    """Load configuration from environment variables.

    Reads service roots MONKEY_BASE_URL, OVIS_BASE_URL and PP_BASE_URL.
    Environment overrides .env.local; short names win within each source.
    Also reads compatible variables matching .env.example:
    - MONKEY_OPENAI_BASE_URL, MONKEY_MODEL, MONKEY_API_KEY
    - OVIS_OPENAI_BASE_URL, OVIS_MODEL, OVIS_API_KEY
    - PP_STRUCTURE_BASE_URL, PP_STRUCTURE_ENDPOINT_PATH, PP_STRUCTURE_TRANSPORT, PADDLE_API_KEY
    - MODEL_CONNECT_TIMEOUT_SECONDS, MODEL_REQUEST_TIMEOUT_SECONDS

    Also supports deprecated variables with warning:
    - MONKEY_CHAT_URL, OVIS_CHAT_URL, PP_STRUCTURE_URL
    """
    env_vars: dict[str, str] = {}

    # Load from .env.local
    env_path = Path.cwd() / ".env.local"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    value = value.strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                        value = value[1:-1]
                    env_vars[key.strip()] = value

    def get_env(key: str, default: str = "") -> str:
        return os.environ.get(key, env_vars.get(key, default))

    def endpoint(short_name: str, compatible_name: str) -> str:
        for source in (os.environ, env_vars):
            for name in (short_name, compatible_name):
                if name in source:
                    return source[name]
        return ""

    # Primary variables (aligned with .env.example)
    monkey_url = endpoint("MONKEY_BASE_URL", "MONKEY_OPENAI_BASE_URL")
    monkey_model = get_env("MONKEY_MODEL", "MonkeyOCRv2")
    monkey_key = get_env("MONKEY_API_KEY", "")

    ovis_url = endpoint("OVIS_BASE_URL", "OVIS_OPENAI_BASE_URL")
    ovis_model = get_env("OVIS_MODEL", "ovis-ocr2")
    ovis_key = get_env("OVIS_API_KEY", "")

    pp_url = endpoint("PP_BASE_URL", "PP_STRUCTURE_BASE_URL")
    pp_key = get_env("PADDLE_API_KEY", "")

    # Deprecated variables (show warning if primary not set)
    if not monkey_url:
        deprecated = get_env("MONKEY_CHAT_URL", "")
        if deprecated:
            print(
                "WARNING: MONKEY_CHAT_URL is deprecated. Use MONKEY_OPENAI_BASE_URL",
                file=sys.stderr,
            )
            monkey_url = deprecated

    if not ovis_url:
        deprecated = get_env("OVIS_CHAT_URL", "")
        if deprecated:
            print(
                "WARNING: OVIS_CHAT_URL is deprecated. Use OVIS_OPENAI_BASE_URL",
                file=sys.stderr,
            )
            ovis_url = deprecated

    if not pp_url:
        deprecated = get_env("PP_STRUCTURE_URL", "")
        if deprecated:
            print(
                "WARNING: PP_STRUCTURE_URL is deprecated. Use PP_STRUCTURE_BASE_URL",
                file=sys.stderr,
            )
            pp_url = deprecated

    return DiscoveryConfig(
        monkey=ModelConfig(base_url=monkey_url, model=monkey_model, api_key=monkey_key),
        ovis=ModelConfig(base_url=ovis_url, model=ovis_model, api_key=ovis_key),
        pp=ModelConfig(base_url=pp_url, api_key=pp_key),
        timeouts=Timeouts(
            connect=int(get_env("MODEL_CONNECT_TIMEOUT_SECONDS", "10")),
            request=int(get_env("MODEL_REQUEST_TIMEOUT_SECONDS", "600")),
        ),
    )


# ============================================================================
# URL Handling
# ============================================================================


def normalize_openai_base_url(url: str) -> str:
    """Normalize OpenAI base URL.

    Ensures the URL ends with exactly /v1.
    Strips any path beyond /v1 (e.g., /v1/chat/completions -> /v1).
    """
    if not url:
        return ""

    url = url.rstrip("/")

    # Parse URL to handle paths correctly
    parsed = urlparse(url)

    segments = parsed.path.strip("/").split("/") if parsed.path.strip("/") else []
    if "v1" in segments:
        segments = segments[: segments.index("v1") + 1]
    else:
        segments.append("v1")
    path = "/" + "/".join(segments)

    # Rebuild URL
    normalized = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )

    return normalized


def openai_endpoint_url(base_url: str, endpoint: str) -> str:
    """Build full URL for an OpenAI endpoint.

    Args:
        base_url: Base URL (may or may not include /v1)
        endpoint: Endpoint path without leading /v1 (e.g., "models", "chat/completions")

    Returns:
        Full URL with exactly one /v1 prefix
    """
    base = normalize_openai_base_url(base_url)
    endpoint = endpoint.lstrip("/")
    if endpoint.startswith("v1/"):
        endpoint = endpoint[3:]
    return f"{base}/{endpoint}"


def openapi_service_root(base_url: str) -> str:
    """Extract service root URL for OpenAPI discovery.

    Removes only the last /v1 path segment if present.

    Example:
        http://host:9000/v1 -> http://host:9000
        http://host:9000 -> http://host:9000
    """
    if not base_url:
        return ""

    parsed = urlparse(base_url)
    path = parsed.path.rstrip("/")

    segments = path.strip("/").split("/") if path.strip("/") else []
    if "v1" in segments:
        path = "/" + "/".join(segments[: segments.index("v1")])
        path = path.rstrip("/")

    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


# Evidence contains hashes and wire metadata, never OCR text or input assets.
ACCESS_MODE = "frp_stcp_loopback"
GENERATED_BY = "scripts/model_contract_discovery.py"
FALLBACK_PATHS = ("/layout-parsing", "/PP-StructureV3")
FALLBACK_TRANSPORTS = ("json_base64", "multipart")


def compute_json_fingerprint(data: Any) -> str:
    """Hash canonical JSON (distinct from raw HTTP response-byte fingerprints)."""
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def compute_file_hash(path: Path) -> str:
    """Hash a local asset without exposing its contents or absolute path."""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def redact_url(url: str) -> str:
    """Remove host, credentials, query and fragment while retaining port/path."""
    parsed = urlparse(url)
    if not url:
        return ""
    host = f"MODEL_SERVER_IP:{parsed.port}" if parsed.port else "MODEL_SERVER_IP"
    return urlunparse((parsed.scheme, host, parsed.path, "", "", ""))


def redact_text(text: str, max_preview: int = 0) -> str:
    """Represent private text using a full digest and length, never a preview."""
    return f"[REDACTED:sha256={hashlib.sha256(text.encode()).hexdigest()}:length={len(text)}]"


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Strip sensitive header values without losing their presence."""
    sensitive = {
        "authorization",
        "proxy-authorization",
        "api-key",
        "x-api-key",
        "token",
        "apikey",
        "cookie",
        "set-cookie",
    }
    return {k: "[REDACTED]" if k.lower() in sensitive else v for k, v in headers.items()}


def redact_base64_images(data: Any, max_length: int = 100) -> Any:
    """Recursively redact images, including nested maps and short data URLs."""
    if isinstance(data, dict):
        return {
            k: redact_text(json.dumps(v, ensure_ascii=False))
            if k.lower()
            in {
                "image",
                "img",
                "img_base64",
                "image_base64",
                "inputimage",
                "outputimages",
                "images",
            }
            else redact_base64_images(v, max_length)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [redact_base64_images(v, max_length) for v in data]
    if isinstance(data, str) and (
        data.startswith("data:")
        or (len(data) > max_length and re.fullmatch(r"[A-Za-z0-9+/=\s]+", data))
    ):
        return redact_text(data)
    return data


def scrub(data: Any, secrets: tuple[str, ...] = (), *, preserve_schema: bool = False) -> Any:
    """Remove credentials, hosts, paths, descriptions, examples and document text."""
    if isinstance(data, dict):
        output: dict[str, Any] = {}
        for key, value in data.items():
            lower = key.lower()
            safe_key = str(scrub(key, secrets, preserve_schema=True))
            if lower in {"servers", "description", "example", "examples", "externaldocs"}:
                continue
            if lower in {
                "authorization",
                "api_key",
                "apikey",
                "token",
                "secret",
                "password",
                "x-api-key",
                "cookie",
                "set-cookie",
            }:
                output[safe_key] = "[REDACTED]"
            elif not preserve_schema and lower in {
                "block_content",
                "rec_texts",
                "markdown",
                "text",
                "errorMsg".lower(),
                "inputimage",
                "outputimages",
                "images",
                "_raw_text",
            }:
                output[safe_key] = redact_text(json.dumps(value, ensure_ascii=False))
            else:
                output[safe_key] = scrub(
                    value,
                    secrets,
                    preserve_schema=preserve_schema
                    or key
                    in {
                        "openapi",
                        "request_schema",
                        "responses",
                        "wire_shape",
                        "observed_wire_shape",
                        "success_observation",
                        "properties",
                    },
                )
        return output
    if isinstance(data, list):
        return [scrub(value, secrets, preserve_schema=preserve_schema) for value in data]
    if isinstance(data, str):
        for secret in secrets:
            if secret:
                data = data.replace(secret, "[REDACTED]")
        if data.startswith("data:") or (
            len(data) > 1000 and re.fullmatch(r"[A-Za-z0-9+/=]+", data)
        ):
            return redact_text(data)
        data = re.sub(r"https?://[^\s\"'<>]+", lambda m: redact_url(m[0]), data)
        data = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "MODEL_SERVER_IP", data)
        data = re.sub(r"(?:/Users/|/home/|[A-Za-z]:\\)[^\s\"']*", "[LOCAL_PATH]", data)
        data = re.sub(r"(?i)Bearer\s+\S+", "Bearer [REDACTED]", data)
    return data


def wire_type(value: Any) -> str:
    """Return a JSON wire type without coercion."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    return "number"


def wire_shape(value: Any) -> dict[str, Any]:
    """Keep the observed shape/counts of arbitrary responses without string values."""
    result: dict[str, Any] = {"type": wire_type(value)}
    if isinstance(value, dict):
        result["properties"] = {str(k): wire_shape(v) for k, v in value.items()}
    elif isinstance(value, list):
        result["count"] = len(value)
        # All distinct shapes are retained; no page content is copied.
        shapes = {}
        for item in value:
            shape = wire_shape(item)
            shapes[compute_json_fingerprint(shape)] = shape
        result["items"] = list(shapes.values())
    return result


def classify_monkey_content(content: Any) -> dict[str, Any]:
    """Classify by parsing, not brackets; strict JSON is distinguished from Python."""
    result: dict[str, Any] = {
        "wire_type": wire_type(content),
        "serialization": "unknown",
        "parsed_type": "unknown",
        "strict_json": False,
    }
    if content is None:
        result["wire_type"] = "unknown"
    parsed: Any = content
    if isinstance(content, list):
        result.update(serialization="json", strict_json=True)
    elif isinstance(content, str):
        try:
            parsed = json.loads(content)
            result.update(serialization="json", strict_json=True)
        except (ValueError, RecursionError):
            try:
                parsed = ast.literal_eval(content.strip())
                if isinstance(parsed, list):
                    result.update(
                        serialization="python_literal_list", safe_parser="ast.literal_eval"
                    )
            except (ValueError, SyntaxError, RecursionError, MemoryError):
                parsed = None
    if isinstance(parsed, list) and all(isinstance(block, dict) for block in parsed):
        result["parsed_type"] = "array<object>"
    return result


def safe_parse_monkey_content(content: Any) -> tuple[list[Any], dict[str, Any]]:
    """Parse literal blocks safely; errors never include the original content."""
    classification = classify_monkey_content(content)
    try:
        parsed = ast.literal_eval(content.strip()) if isinstance(content, str) else content
    except (ValueError, SyntaxError, RecursionError, MemoryError):
        raise ValueError("MONKEY_LITERAL_PARSE_FAILED") from None
    if not isinstance(parsed, list) or not all(isinstance(block, dict) for block in parsed):
        raise ValueError("MONKEY_BLOCK_ARRAY_REQUIRED")
    return parsed, classification


def validate_monkey_block(block: Any, page_width: int = 0, page_height: int = 0) -> dict[str, Any]:
    """Validate the declared normalized_1000 contract, not infer units from ranges."""
    if not isinstance(block, dict):
        return {"valid": False, "error": "block is not a dict"}
    bbox = block.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return {"valid": False, "error": "bbox missing or wrong length"}
    valid = all(
        isinstance(v, int | float)
        and not isinstance(v, bool)
        and math.isfinite(v)
        and 0 <= v <= 1000
        for v in bbox
    )
    if valid:
        valid = bbox[0] <= bbox[2] and bbox[1] <= bbox[3]
    valid = valid and isinstance(block.get("label"), str)
    return {
        "valid": valid,
        "coordinate_space": "normalized_1000",
        "coordinate_space_basis": "declared_model_contract_with_range_validation",
        "warnings": [] if valid else ["INVALID_BBOX_OR_LABEL"],
    }


@dataclass
class RequestMetadata:
    """Body-free HTTP evidence. Fingerprints hash the original response bytes."""

    request_id: str
    started_at: str
    duration_ms: float = 0.0
    method: str = ""
    url: str = ""
    request_content_type: str = ""
    response_status: int = 0
    response_content_type: str = ""
    redirect_count: int = 0
    response_fingerprint: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Expose non-sensitive request metadata for reproducible evidence."""
        return asdict(self)


class HttpClient:
    """Serial HTTP with no redirects, no retries, injectable offline transport."""

    def __init__(self, timeouts: Timeouts, transport: httpx.BaseTransport | None = None) -> None:
        """Use all timeout components and never follow OpenAPI server redirects."""
        self.client = httpx.Client(
            timeout=httpx.Timeout(
                connect=timeouts.connect,
                read=timeouts.request,
                write=timeouts.request,
                pool=timeouts.connect,
            ),
            follow_redirects=False,
            transport=transport,
        )
        self.requests: list[dict[str, Any]] = []

    def __enter__(self) -> HttpClient:
        """Return this client for deterministic close semantics."""
        return self

    def __exit__(self, *_args: Any) -> None:
        """Close even when orchestration fails."""
        self.close()

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any], RequestMetadata]:
        """Make one loopback request; exceptions and non-JSON bodies are type-only."""
        parsed = urlparse(url)
        if (
            parsed.hostname != "127.0.0.1"
            or parsed.port not in {9000, 8000, 8080}
            or parsed.scheme != "http"
            or parsed.username
            or parsed.password
        ):
            raise ValueError("BLOCKED_NON_LOOPBACK_ENDPOINT")
        meta = RequestMetadata(
            str(uuid.uuid4()), datetime.now(UTC).isoformat(), method=method, url=redact_url(url)
        )
        started = time.monotonic()
        options: dict[str, Any] = {"headers": headers or {}, "params": params}
        if files is not None:
            options.update(files=files, data=data)
        elif json_data is not None:
            options["json"] = json_data
        elif data is not None:
            options["data"] = data
        body: dict[str, Any] = {}
        try:
            request = self.client.build_request(method, url, **options)
            request.headers["X-Request-ID"] = meta.request_id
            meta.request_content_type = request.headers.get("content-type", "")
            response = self.client.send(request)
            meta.response_status = response.status_code
            meta.response_content_type = response.headers.get("content-type", "")
            meta.response_fingerprint = hashlib.sha256(response.content).hexdigest()
            meta.redirect_count = len(response.history)
            if 300 <= response.status_code < 400:
                meta.error = "REDIRECT_NOT_FOLLOWED"
            try:
                decoded = response.json()
                if isinstance(decoded, dict):
                    body = decoded
                else:
                    meta.error = "NON_OBJECT_JSON_RESPONSE"
            except ValueError:
                meta.error = "NON_JSON_RESPONSE"
        except httpx.HTTPError as error:
            meta.error = type(error).__name__
        finally:
            meta.duration_ms = round((time.monotonic() - started) * 1000, 3)
            self.requests.append(meta.to_dict())
        return meta.response_status, body, meta

    def get(
        self, url: str, headers: dict[str, str] | None = None
    ) -> tuple[int, dict[str, Any], RequestMetadata]:
        """GET with metadata and optional authentication."""
        return self.request("GET", url, headers=headers)

    def post(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        json_data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any], RequestMetadata]:
        """POST, preserving empty JSON and actual multipart Content-Type."""
        return self.request(
            "POST", url, headers=headers, json_data=json_data, files=files, data=data, params=params
        )

    def close(self) -> None:
        """Release network resources."""
        self.client.close()


def resolve_refs(value: Any, document: dict[str, Any], seen: tuple[str, ...] = ()) -> Any:
    """Resolve only local OpenAPI refs without fetching external resources."""
    if isinstance(value, list):
        return [resolve_refs(v, document, seen) for v in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        ref = value["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/") or ref in seen:
            raise ValueError("OPENAPI_UNRESOLVED_REFERENCE")
        target: Any = document
        try:
            for part in ref[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError):
            raise ValueError("OPENAPI_UNRESOLVED_REFERENCE") from None
        resolved = resolve_refs(target, document, (*seen, ref))
        return {
            **resolved,
            **{k: resolve_refs(v, document, seen) for k, v in value.items() if k != "$ref"},
        }
    result = {k: resolve_refs(v, document, seen) for k, v in value.items()}
    if "allOf" in result:
        # Combine object properties/required fields while retaining other constraints.
        properties = dict(result.get("properties", {}))
        required = list(result.get("required", []))
        for schema in result["allOf"]:
            properties.update(schema.get("properties", {}))
            required.extend(schema.get("required", []))
        if properties:
            result["properties"] = properties
            result["required"] = list(dict.fromkeys(required))
    return result


def normalize_openapi(document: dict[str, Any]) -> dict[str, Any]:
    """Extract version, paths and wire schemas, omitting servers and prose/examples."""
    normalized: dict[str, Any] = {
        "openapi_version": document.get("openapi"),
        "info": {k: document.get("info", {}).get(k) for k in ("title", "version")},
        "paths": {},
        "incomplete": False,
    }
    for path, item in document.get("paths", {}).items():
        if not isinstance(item, dict):
            normalized["incomplete"] = True
            continue
        operations: dict[str, Any] = {}
        for method, operation in item.items():
            if method not in {"get", "post", "put", "delete", "patch", "options", "head"}:
                continue
            try:
                resolved = resolve_refs(operation, document)
                parameters = resolve_refs(item.get("parameters", []), document)
                operations[method] = {
                    "operationId": resolved.get("operationId"),
                    "requestBody": resolved.get("requestBody", {}),
                    "parameters": parameters + resolved.get("parameters", []),
                    "responses": resolved.get("responses", {}),
                    "deprecated": resolved.get("deprecated", False),
                }
            except ValueError:
                operations[method] = {"incomplete": True}
                normalized["incomplete"] = True
        normalized["paths"][path] = operations
    return dict(scrub(normalized, preserve_schema=True))


def _binary_schema(schema: dict[str, Any]) -> bool:
    return schema.get("format") in {"binary", "byte"} or any(
        _binary_schema(s) for key in ("anyOf", "oneOf", "allOf") for s in schema.get(key, [])
    )


def discover_pp_candidates_from_openapi(openapi_spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Discover exact POST upload paths, refs, content types and field names."""
    normalized = normalize_openapi(openapi_spec)
    candidates: list[dict[str, Any]] = []
    for path, item in normalized["paths"].items():
        operation = item.get("post", {})
        if operation.get("incomplete"):
            continue
        for media, content in operation.get("requestBody", {}).get("content", {}).items():
            if media not in {"application/json", "multipart/form-data"}:
                continue
            schema = content.get("schema", {})
            properties = schema.get("properties", {})
            fields = [
                name
                for name, prop in properties.items()
                if _binary_schema(prop) or name.lower() in {"file", "image", "image_base64"}
            ]
            if not fields:
                continue
            candidates.append(
                {
                    "path": path,
                    "method": "POST",
                    "transport": "json_base64" if media == "application/json" else "multipart",
                    "content_type": media,
                    "file_field": fields[0],
                    "file_type_field": "fileType" if "fileType" in properties else None,
                    "required": schema.get("required", []),
                    "request_schema": schema,
                    "query_parameters": [
                        p for p in operation.get("parameters", []) if p.get("in") == "query"
                    ],
                    "responses": operation.get("responses", {}),
                    "operation_id": operation.get("operationId"),
                    "deprecated": operation.get("deprecated", False),
                    "source": "openapi",
                }
            )
    return sorted(candidates, key=lambda candidate: candidate["deprecated"])


def build_pp_json_payload(file_base64: str, file_type: int = 1) -> dict[str, Any]:
    """Build the documented JSON image request, always including fileType."""
    return {"file": file_base64, "fileType": file_type}


def build_pp_error_probes(file_base64: str = "") -> list[dict[str, Any]]:
    """Three harmless validation errors; the type probe retains a valid full image."""
    return [
        {"name": "missing_file", "payload": {"fileType": 1}},
        {"name": "invalid_file_type", "payload": {"file": file_base64, "fileType": 99}},
        {"name": "invalid_file", "payload": {"file": "not-valid-base64!!!", "fileType": 1}},
    ]


def pp_success(status: int, body: dict[str, Any]) -> bool:
    """Require transport and application success plus the real PP result shape."""
    return (
        200 <= status < 300
        and body.get("errorCode") == 0
        and isinstance(body.get("result"), dict)
        and isinstance(body["result"].get("layoutParsingResults"), list)
        and bool(body["result"]["layoutParsingResults"])
    )


def error_observation(status: int, body: dict[str, Any], meta: RequestMetadata) -> dict[str, Any]:
    """Keep HTTP and body error codes independent and omit error-message text."""
    code = body.get("errorCode")
    return {
        "http_status": status,
        "application_error_code": code,
        "error_msg_wire_type": wire_type(body.get("errorMsg")),
        "response_content_type": meta.response_content_type,
        "response_fingerprint": meta.response_fingerprint,
        "request_id": meta.request_id,
        "duration_ms": meta.duration_ms,
        "wire_shape": wire_shape(body),
        "error_observed": bool(
            not meta.error
            and (400 <= status < 600 or (200 <= status < 300 and code not in (None, 0)))
        ),
    }


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _save_response(
    output: Path,
    name: str,
    body: dict[str, Any],
    meta: RequestMetadata,
    secrets: tuple[str, ...],
    *,
    openapi: bool = False,
) -> None:
    # Even ignored evidence contains no full OCR/Base64 or credentials.
    if openapi:
        response = scrub(body, secrets, preserve_schema=True)
    else:
        response = {"wire_shape": wire_shape(body)}
        for key in ("object", "model", "usage", "system_fingerprint", "errorCode"):
            if key in body:
                response[key] = scrub(body[key], secrets)
        if isinstance(body.get("data"), list):
            response["model_metadata"] = scrub(
                [
                    {k: item.get(k) for k in ("id", "max_model_len", "version", "revision")}
                    for item in body["data"]
                    if isinstance(item, dict)
                ],
                secrets,
            )
            response["model_ids"] = scrub(
                [m.get("id") for m in body["data"] if isinstance(m, dict)],
                secrets,
            )
        if (
            isinstance(body.get("choices"), list)
            and body["choices"]
            and isinstance(body["choices"][0], dict)
        ):
            choice = body["choices"][0]
            response["finish_reason"] = choice.get("finish_reason")
            message = choice.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            response["content_wire_type"] = wire_type(content)
            if isinstance(content, str):
                response["content_sha256"] = hashlib.sha256(content.encode()).hexdigest()
                response["content_length"] = len(content)
                if name.startswith("monkey"):
                    response["classification"] = classify_monkey_content(content)
        response = scrub(response, secrets)
    _write_json(
        output / f"{name}.raw.redacted.json",
        {
            "response": response,
            "metadata": meta.to_dict(),
            "response_fingerprint_algorithm": "sha256_http_response_bytes",
            "redacted_response_fingerprint": compute_json_fingerprint(response),
        },
    )


def _headers(model: ModelConfig) -> dict[str, str]:
    return {"Authorization": f"Bearer {model.api_key}"} if model.api_key else {}


def observe_models(
    client: HttpClient,
    model: ModelConfig,
    expected: str,
    output: Path,
    name: str,
    secrets: tuple[str, ...],
) -> dict[str, Any]:
    """Check exact deployed model identity before any inference requests."""
    status, body, meta = client.get(openai_endpoint_url(model.base_url, "models"), _headers(model))
    _save_response(output, f"{name}.models", body, meta, secrets)
    entries = body.get("data")
    ids = [m.get("id") for m in entries if isinstance(m, dict)] if isinstance(entries, list) else []
    endpoint_ok = status == 200 and isinstance(entries, list) and not meta.error
    identity_ok = endpoint_ok and expected in ids and model.model == expected
    contract_status = (
        "BLOCKED_MODELS_ENDPOINT_UNAVAILABLE"
        if not endpoint_ok
        else "pending"
        if identity_ok
        else "BLOCKED_MODEL_IDENTITY_MISMATCH"
    )
    matched = (
        next(
            (entry for entry in entries if isinstance(entry, dict) and entry.get("id") == expected),
            {},
        )
        if isinstance(entries, list)
        else {}
    )
    return {
        "model_metadata": scrub(
            {
                k: matched.get(k)
                for k in (
                    "max_model_len",
                    "version",
                    "revision",
                )
            },
            secrets,
        ),
        "expected_model_id": expected,
        "actual_model_ids": scrub(ids, secrets),
        "response_object": body.get("object"),
        "model_id": expected if identity_ok else None,
        "identity_verified": identity_ok,
        "request_id": meta.request_id,
        "response_fingerprint": meta.response_fingerprint,
        "http_status": status,
        "contract_status": contract_status,
    }


def observe_chat(body: dict[str, Any], service_name: str) -> dict[str, Any]:
    """Extract content-free chat facts; Monkey and Ovis use different contracts."""
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("CHAT_CHOICES_MISSING")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("CHAT_MESSAGE_OBJECT_REQUIRED")
    content = message.get("content")
    result: dict[str, Any] = {
        "response_object": body.get("object"),
        "model": body.get("model"),
        "finish_reason": choice.get("finish_reason"),
        "usage": body.get("usage"),
        "system_fingerprint": body.get("system_fingerprint"),
    }
    if service_name == "monkey":
        parsed, classification = safe_parse_monkey_content(content)
        if (
            classification["wire_type"] != "string"
            or classification["serialization"] != "python_literal_list"
            or classification["strict_json"]
            or not parsed
            or not all(validate_monkey_block(block)["valid"] for block in parsed)
        ):
            raise ValueError("MONKEY_WIRE_CONTRACT_MISMATCH")
        result["wire_contract"] = {
            **classification,
            "parsed_block_count": len(parsed),
            "coordinate_space": "normalized_1000",
            "coordinate_space_basis": "declared_contract_range_checked",
        }
    else:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("OVIS_MARKDOWN_STRING_REQUIRED")
        result["wire_contract"] = {
            "wire_type": "string",
            "serialization": "markdown",
            "content_length": len(content),
            "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
        }
    if result["finish_reason"] != "stop":
        raise ValueError("CHAT_INCOMPLETE_FINISH_REASON")
    return result


def discover_openai_service(
    client: HttpClient,
    model: ModelConfig,
    name: str,
    identity: dict[str, Any],
    image_base64: str,
    media: str,
    output: Path,
    secrets: tuple[str, ...],
) -> dict[str, Any]:
    """Observe OpenAPI, one image chat and one harmless wrong-model error."""
    result = {
        **identity,
        "provider_type": "openai_compatible",
        "base_url_template": redact_url(model.base_url),
        "errors": [],
    }
    status, body, meta = client.get(
        openapi_service_root(model.base_url) + "/openapi.json", _headers(model)
    )
    _save_response(output, f"{name}.openapi", body, meta, secrets, openapi=True)
    result["openapi"] = {
        "available": status == 200 and isinstance(body.get("openapi"), str),
        "version": body.get("openapi"),
        "info_version": body.get("info", {}).get("version"),
        "response_fingerprint": meta.response_fingerprint,
    }
    prompt = (
        "Please output the categories and coordinates of the document elements in reading order."
        if name == "monkey"
        else "Extract readable content in reading order as Markdown. Preserve original text, "
        "numbers, units and symbols. Do not translate, correct, summarize or infer."
    )
    payload = {
        "model": model.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media};base64,{image_base64}"},
                    },
                ],
            }
        ],
        "max_tokens": 2048 if name == "monkey" else 8192,
    }
    result["request_parameters"] = {
        "model": model.model,
        "max_tokens": payload["max_tokens"],
        "input_media_type": media,
    }
    url = openai_endpoint_url(model.base_url, "chat/completions")
    status, body, meta = client.post(url, headers=_headers(model), json_data=payload)
    _save_response(output, f"{name}.chat", body, meta, secrets)
    result["chat_response_fingerprint"] = meta.response_fingerprint
    try:
        if status != 200 or meta.error or body.get("model") != model.model:
            raise ValueError("CHAT_HTTP_OR_MODEL_MISMATCH")
        chat = observe_chat(body, name)
        result.update(scrub(chat, secrets))
    except ValueError as error:
        result["contract_status"] = str(error)
        result["errors"].append(str(error))
        return result
    status, body, meta = client.post(
        url,
        headers=_headers(model),
        json_data={
            "model": "t0015-invalid-model",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        },
    )
    _save_response(output, f"{name}.error", body, meta, secrets)
    result["error_probe"] = error_observation(status, body, meta)
    result["contract_status"] = (
        "verified" if result["error_probe"]["error_observed"] else "BLOCKED_ERROR_CONTRACT"
    )
    return result


def _candidate_request(
    client: HttpClient,
    model: ModelConfig,
    candidate: dict[str, Any],
    image: bytes,
    media: str,
    payload: dict[str, Any],
    *,
    error_probe: bool = False,
) -> tuple[int, dict[str, Any], RequestMetadata]:
    path = candidate["path"]
    if (
        not path.startswith("/")
        or path.startswith("//")
        or ".." in path
        or any(c in path for c in ("?", "#", "\\", "{", "}"))
    ):
        raise ValueError("UNSAFE_OPENAPI_PATH")
    params: dict[str, Any] = {}
    for parameter in candidate.get("query_parameters", []):
        schema = parameter.get("schema", {})
        if parameter.get("required"):
            if "default" not in schema:
                raise ValueError("OPENAPI_REQUIRED_QUERY_UNRESOLVED")
            params[parameter["name"]] = schema["default"]
    schema = candidate.get("request_schema", {})
    full_payload = dict(payload)
    for name in candidate.get("required", []):
        if name not in {candidate["file_field"], "fileType"}:
            field_schema = schema.get("properties", {}).get(name, {})
            if "default" not in field_schema:
                raise ValueError("OPENAPI_REQUIRED_FIELD_UNRESOLVED")
            full_payload[name] = field_schema["default"]
    url = openapi_service_root(model.base_url) + path
    if candidate["transport"] == "json_base64":
        # Explicit required PP JSON contract; do not guess an alternate field name.
        if candidate["file_field"] != "file":
            raise ValueError("CONTRACT_RUNTIME_DIVERGENCE")
        if schema and not error_probe:
            try:
                Draft202012Validator(schema).validate(full_payload)
            except (ValidationError, Unresolvable):
                raise ValueError("CONTRACT_RUNTIME_DIVERGENCE") from None
        return client.post(url, _headers(model), json_data=full_payload, params=params)
    file_field = candidate["file_field"]
    files: dict[str, Any] = {}
    if "file" in payload:
        content = b"not-valid-base64!!!" if payload["file"] == "not-valid-base64!!!" else image
        files[file_field] = ("input" + (".png" if media == "image/png" else ".jpg"), content, media)
    # A no-file error still uses multipart encoding, with fileType as a form part.
    for name, value in full_payload.items():
        if name != "file" and (name != "fileType" or candidate.get("file_type_field")):
            files[name] = (None, str(value))
    if not files:
        files["fileType"] = (None, "1")
    return client.post(url, _headers(model), files=files, params=params)


def probe_pp_candidate(
    client: HttpClient,
    model: ModelConfig,
    candidate: dict[str, Any],
    image: bytes,
    media: str,
    output: Path,
    index: int,
    secrets: tuple[str, ...],
) -> dict[str, Any]:
    """Execute one documented or bounded request, keeping success and failure evidence."""
    probe = {
        **candidate,
        "http_status": 0,
        "application_error_code": None,
        "success_predicate": False,
        "failure_category": "",
        "duration_ms": 0.0,
        "response_fingerprint": "",
        "response_content_type": "",
    }
    try:
        status, body, meta = _candidate_request(
            client,
            model,
            candidate,
            image,
            media,
            build_pp_json_payload(base64.b64encode(image).decode(), 1),
        )
    except ValueError as error:
        probe["failure_category"] = str(error)
        return probe
    _save_response(output, f"pp.probe-{index}", body, meta, secrets)
    success = pp_success(status, body) and not meta.error
    # Verify actual successful JSON against the documented response schema if provided.
    schema = (
        candidate.get("responses", {})
        .get(str(status), {})
        .get("content", {})
        .get("application/json", {})
        .get("schema")
    )
    divergence = False
    if success and schema:
        try:
            Draft202012Validator(schema).validate(body)
        except (ValidationError, Unresolvable):
            divergence = True
            success = False
    probe.update(
        http_status=status,
        application_error_code=body.get("errorCode"),
        response_content_type=meta.response_content_type,
        duration_ms=meta.duration_ms,
        response_fingerprint=meta.response_fingerprint,
        request_id=meta.request_id,
        success_predicate=success,
        observed_wire_shape=wire_shape(body),
        failure_category=(
            "CONTRACT_RUNTIME_DIVERGENCE"
            if divergence
            else meta.error or ("" if success else "HTTP_OR_APPLICATION_ERROR")
        ),
    )
    return probe


def discover_pp_service(
    client: HttpClient,
    config: DiscoveryConfig,
    image: bytes,
    media: str,
    output: Path,
    secrets: tuple[str, ...],
) -> dict[str, Any]:
    """Prefer exact OpenAPI candidates; only incomplete discovery uses ADR-007 fallback."""
    model = config.pp
    status, body, meta = client.get(
        openapi_service_root(model.base_url) + "/openapi.json", _headers(model)
    )
    _save_response(output, "pp.openapi", body, meta, secrets, openapi=True)
    available = status == 200 and not meta.error and isinstance(body.get("openapi"), str)
    normalized = normalize_openapi(body) if available else {}
    candidates = discover_pp_candidates_from_openapi(body) if available else []
    # T0015 only probes whole-document layout endpoints, never specialty tasks.
    candidates = [
        c
        for c in candidates
        if c["path"] in FALLBACK_PATHS
        or any(word in c["path"].lower() for word in ("layout-parsing", "structure"))
    ]
    needs_fallback = not candidates or normalized.get("incomplete", False)
    documented_count = len(candidates)
    if needs_fallback:
        for path in config.pp_candidate_paths:
            if path not in FALLBACK_PATHS:
                raise ValueError("UNBOUNDED_PP_PROBE_PATH")
            for transport in config.pp_candidate_transports:
                if transport not in FALLBACK_TRANSPORTS:
                    raise ValueError("UNBOUNDED_PP_TRANSPORT")
                if any(c["path"] == path and c["transport"] == transport for c in candidates):
                    continue
                candidates.append(
                    {
                        "path": path,
                        "method": "POST",
                        "transport": transport,
                        "file_field": "file",
                        "file_type_field": "fileType",
                        "source": "bounded_runtime_probe",
                    }
                )
    result: dict[str, Any] = {
        "provider_type": "paddle_pipeline",
        "base_url_template": redact_url(model.base_url),
        "openapi_available": available,
        "openapi_fingerprint": meta.response_fingerprint,
        "openapi": normalized,
        "probe_matrix": [],
        "alternatives": [],
        "contract_status": "BLOCKED_PP_CONTRACT_UNRESOLVED",
        "system_fingerprint": None,
        "version": normalized.get("info", {}).get("version"),
        "submodel_endpoint_enumeration": "not_tested_in_T0015",
    }
    for index, candidate in enumerate(candidates):
        result["probe_matrix"].append(
            probe_pp_candidate(
                client,
                model,
                candidate,
                image,
                media,
                output,
                index,
                secrets,
            )
        )
    # A documented candidate failure is visible divergence, never overwritten by fallback success.
    if any(not p["success_predicate"] for p in result["probe_matrix"][:documented_count]):
        result["contract_status"] = "CONTRACT_RUNTIME_DIVERGENCE"
        return result
    successes = [p for p in result["probe_matrix"] if p["success_predicate"]]
    if not successes:
        return result
    primary = successes[0]
    result.update(
        endpoint_path=primary["path"],
        method="POST",
        transport=primary["transport"],
        file_field=primary["file_field"],
        file_type_field=primary.get("file_type_field"),
        request_schema=primary.get("request_schema", {}),
        success_response_fingerprint=primary["response_fingerprint"],
        success_observation=primary["observed_wire_shape"],
        contract_source=(
            "openapi_with_runtime_verification"
            if primary["source"] == "openapi"
            else "bounded_runtime_probe"
        ),
        selection_reason="documented_non_deprecated_order_then_bounded_order",
    )
    result["alternatives"] = [
        {
            "path": p["path"],
            "transport": p["transport"],
            "kind": "compatibility_alternative",
            "response_fingerprint": p["response_fingerprint"],
        }
        for p in successes[1:]
    ]
    result["error_probes"] = []
    for probe in build_pp_error_probes(base64.b64encode(image).decode()):
        status, body, meta = _candidate_request(
            client, model, primary, image, media, probe["payload"], error_probe=True
        )
        _save_response(output, "pp.error-" + probe["name"], body, meta, secrets)
        result["error_probes"].append(
            {"name": probe["name"], **error_observation(status, body, meta)}
        )
    if not all(error["error_observed"] for error in result["error_probes"]):
        result["contract_status"] = "BLOCKED_ERROR_CONTRACT"
    else:
        result["contract_status"] = (
            "verified_from_openapi"
            if primary["source"] == "openapi"
            else "verified_runtime_without_openapi"
        )
    return result


def assert_live_preconditions(
    config: DiscoveryConfig,
    root: Path,
    *,
    confirmed_no_auth: bool = False,
    confirmed_key_rotation: bool = False,
) -> None:
    """Require explicit operator security confirmation plus local-only credential storage."""
    if not confirmed_no_auth and not confirmed_key_rotation:
        raise ValueError("SECURITY_CONFIRMATION_REQUIRED_KEY_ROTATION_OR_NO_AUTH")
    env_path = root / ".env.local"
    if not env_path.is_file() or stat.S_IMODE(env_path.stat().st_mode) != 0o600:
        raise ValueError("ENV_LOCAL_MUST_BE_0600")
    if subprocess.check_output(["git", "ls-files", ".env.local"], cwd=root).strip():
        raise ValueError("ENV_LOCAL_IS_TRACKED")
    keys = tuple(m.api_key for m in (config.monkey, config.ovis, config.pp) if m.api_key)
    if confirmed_no_auth and keys:
        raise ValueError("NO_AUTH_MODE_HAS_CREDENTIALS")
    if confirmed_key_rotation:
        local_values = {
            line.partition("=")[2].strip().strip("\"'")
            for line in env_path.read_text().splitlines()
            if "=" in line
        }
        if not keys or any(key not in local_values for key in keys):
            raise ValueError("CREDENTIALS_MUST_EXIST_ONLY_IN_ENV_LOCAL")
        for name in ("MONKEY_API_KEY", "OVIS_API_KEY", "PADDLE_API_KEY"):
            if os.environ.get(name):
                raise ValueError("CREDENTIAL_ENV_OVERRIDE_FORBIDDEN")
    for name in ("NO_PROXY", "no_proxy"):
        if not {"127.0.0.1", "localhost"}.issubset(set(os.environ.get(name, "").split(","))):
            raise ValueError("LOOPBACK_NO_PROXY_REQUIRED")
    for model, port in ((config.monkey, 9000), (config.ovis, 8000), (config.pp, 8080)):
        parsed = urlparse(model.base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port != port
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("BLOCKED_NON_LOOPBACK_CONFIGURATION")
    for raw in subprocess.check_output(["git", "ls-files", "-z"], cwd=root).split(b"\0"):
        if raw:
            path = root / raw.decode()
            if path.is_file() and any(key.encode() in path.read_bytes() for key in keys):
                raise ValueError("CREDENTIAL_PRESENT_IN_TRACKED_FILE")


def _git_value(root: Path, *args: str) -> str | None:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def run_discovery(
    config: DiscoveryConfig,
    output_dir: Path,
    test_image: Path,
    promote_artifacts: bool = False,
    *,
    transport: httpx.BaseTransport | None = None,
    repository_root: Path | None = None,
    confirmed_no_auth: bool = False,
    confirmed_key_rotation: bool = False,
) -> dict[str, Any]:
    """Run one serial, fail-closed discovery and persist matching status/evidence."""
    root = (repository_root or Path.cwd()).resolve()
    if transport is None:
        assert_live_preconditions(
            config,
            root,
            confirmed_no_auth=confirmed_no_auth,
            confirmed_key_rotation=confirmed_key_rotation,
        )
        allowed = root / "tmp/model-contract-discovery"
        if not output_dir.resolve().is_relative_to(allowed):
            raise ValueError("EVIDENCE_MUST_BE_IN_IGNORED_RUN_DIRECTORY")
        if (
            not subprocess.run(
                ["git", "check-ignore", "--quiet", str(output_dir)], cwd=root, check=False
            ).returncode
            == 0
        ):
            raise ValueError("EVIDENCE_DIRECTORY_NOT_GITIGNORED")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("RUN_DIRECTORY_ALREADY_CONTAINS_EVIDENCE")
    image = test_image.read_bytes()
    if image.startswith(b"\xff\xd8\xff"):
        media = "image/jpeg"
    elif image.startswith(b"\x89PNG\r\n\x1a\n"):
        media = "image/png"
    else:
        raise ValueError("INPUT_MUST_BE_JPEG_OR_PNG")
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    started = datetime.now(UTC)
    run_id = (
        output_dir.name
        if re.fullmatch(r"t0015-[A-Za-z0-9-]+", output_dir.name)
        else f"t0015-mac-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    )
    secrets = tuple(m.api_key for m in (config.monkey, config.ovis, config.pp) if m.api_key)
    result: dict[str, Any] = {
        "schema_version": "2.0",
        "run_id": run_id,
        "started_at": started.isoformat(),
        "completed_at": None,
        "repository_head": _git_value(root, "rev-parse", "HEAD"),
        "branch": _git_value(root, "branch", "--show-current"),
        "operating_system": "macOS" if sys.platform == "darwin" else sys.platform,
        "python_version": sys.version.split()[0],
        "httpx_version": httpx.__version__,
        "access_mode": ACCESS_MODE,
        "execution_mode": "mock" if transport else "live",
        "authentication_mode": "none" if not secrets else "api_key",
        "security_confirmation": "no_auth_required"
        if confirmed_no_auth
        else "key_rotation_confirmed"
        if confirmed_key_rotation
        else "mock_only",
        "input_file_sha256": hashlib.sha256(image).hexdigest(),
        "input_size_bytes": len(image),
        "input_media_type": media,
        "services": {},
        "requests": [],
        "overall_status": "IN_PROGRESS",
        "generated_by": GENERATED_BY,
        "tool_source_sha256": compute_file_hash(Path(__file__)),
    }
    client = HttpClient(config.timeouts, transport=transport)
    try:
        identities = {}
        for name, model, expected in (
            ("monkey", config.monkey, "MonkeyOCRv2"),
            ("ovis", config.ovis, "ovis-ocr2"),
        ):
            identities[name] = observe_models(client, model, expected, output_dir, name, secrets)
            result["services"][name] = identities[name]
        if not all(identity["identity_verified"] for identity in identities.values()):
            result["overall_status"] = (
                "BLOCKED_MODELS_ENDPOINT_UNAVAILABLE"
                if any(
                    identity["contract_status"] == "BLOCKED_MODELS_ENDPOINT_UNAVAILABLE"
                    for identity in identities.values()
                )
                else "BLOCKED_MODEL_IDENTITY_MISMATCH"
            )
        else:
            for name, model in (("monkey", config.monkey), ("ovis", config.ovis)):
                result["services"][name] = discover_openai_service(
                    client,
                    model,
                    name,
                    identities[name],
                    base64.b64encode(image).decode(),
                    media,
                    output_dir,
                    secrets,
                )
            result["services"]["paddle"] = discover_pp_service(
                client,
                config,
                image,
                media,
                output_dir,
                secrets,
            )
            statuses = [s["contract_status"] for s in result["services"].values()]
            if (
                len(statuses) == 3
                and statuses[:2] == ["verified", "verified"]
                and statuses[2] in {"verified_from_openapi", "verified_runtime_without_openapi"}
            ):
                result["overall_status"] = "ACCEPTED"
            elif "CONTRACT_RUNTIME_DIVERGENCE" in statuses:
                result["overall_status"] = "CONTRACT_RUNTIME_DIVERGENCE"
            else:
                result["overall_status"] = "BLOCKED_CONTRACT_UNRESOLVED"
    except (ValueError, KeyError, TypeError) as error:
        # Persist a failed run, without serializing potentially sensitive exception messages.
        result["overall_status"] = "BLOCKED_DISCOVERY_ERROR"
        result["error_category"] = type(error).__name__
    finally:
        client.close()
        result["completed_at"] = datetime.now(UTC).isoformat()
        result["requests"] = client.requests
        if result["overall_status"] == "ACCEPTED" and any(
            not request["response_fingerprint"] for request in client.requests
        ):
            result["overall_status"] = "BLOCKED_INCOMPLETE_EVIDENCE"
        result = scrub(result, secrets)
        _write_json(output_dir / "discovered-model-contracts.json", result)
        (output_dir / "run-results.sha256").write_text(compute_json_fingerprint(result) + "\n")
        _write_json(
            output_dir / "run-metadata.json",
            {k: v for k, v in result.items() if k not in {"services", "requests"}},
        )
    if promote_artifacts:
        if result["overall_status"] != "ACCEPTED":
            return result
        promote_sanitized_artifacts(
            output_dir, root / "specs", root / "tests/fixtures/model_contracts"
        )
    return result


def promote_sanitized_artifacts(
    source_dir: Path, specs_dir: Path, fixtures_dir: Path
) -> dict[str, list[str]]:
    """Generate all public artifacts from one successful run and its checked evidence."""
    result = json.loads((source_dir / "discovered-model-contracts.json").read_text())
    if result.get("overall_status") != "ACCEPTED" or set(result.get("services", {})) != {
        "monkey",
        "ovis",
        "paddle",
    }:
        raise ValueError("PROMOTION_REQUIRES_ACCEPTED_COMPLETE_RUN")
    digest_path = source_dir / "run-results.sha256"
    if not digest_path.is_file() or digest_path.read_text().strip() != compute_json_fingerprint(
        result
    ):
        raise ValueError("RUN_RESULTS_DIGEST_MISMATCH")
    statuses = [
        result["services"][name]["contract_status"] for name in ("monkey", "ovis", "paddle")
    ]
    if statuses[:2] != ["verified", "verified"] or statuses[2] not in {
        "verified_from_openapi",
        "verified_runtime_without_openapi",
    }:
        raise ValueError("PROMOTION_REQUIRES_VERIFIED_SERVICES")
    requests = result["requests"]
    fingerprints = {request["response_fingerprint"] for request in requests}
    if not fingerprints or "" in fingerprints:
        raise ValueError("PROMOTION_REQUIRES_RESPONSE_FINGERPRINTS")
    evidence: dict[str, str] = {}
    for path in source_dir.glob("*.raw.redacted.json"):
        raw = json.loads(path.read_text())
        metadata = raw["metadata"]
        if compute_json_fingerprint(raw["response"]) != raw["redacted_response_fingerprint"]:
            raise ValueError("EVIDENCE_DIGEST_MISMATCH")
        if metadata not in requests:
            raise ValueError("EVIDENCE_REQUEST_MISMATCH")
        evidence[metadata["request_id"]] = metadata["response_fingerprint"]
    if set(evidence) != {request["request_id"] for request in requests}:
        raise ValueError("PROMOTION_EVIDENCE_INCOMPLETE")
    monkey, ovis, pp = (result["services"][name] for name in ("monkey", "ovis", "paddle"))
    observations: dict[str, tuple[Any, list[str]]] = {
        "monkey.models.observed.json": (
            {k: monkey[k] for k in ("model_id", "actual_model_ids", "response_object")},
            [monkey["response_fingerprint"]],
        ),
        "monkey.chat.observed.json": (
            {
                k: monkey.get(k)
                for k in (
                    "response_object",
                    "model",
                    "wire_contract",
                    "finish_reason",
                    "usage",
                    "system_fingerprint",
                    "error_probe",
                )
            },
            [monkey["chat_response_fingerprint"], monkey["error_probe"]["response_fingerprint"]],
        ),
        "ovis.models.observed.json": (
            {k: ovis[k] for k in ("model_id", "actual_model_ids", "response_object")},
            [ovis["response_fingerprint"]],
        ),
        "ovis.chat.observed.json": (
            {
                k: ovis.get(k)
                for k in (
                    "response_object",
                    "model",
                    "wire_contract",
                    "finish_reason",
                    "usage",
                    "system_fingerprint",
                    "error_probe",
                )
            },
            [ovis["chat_response_fingerprint"], ovis["error_probe"]["response_fingerprint"]],
        ),
        "pp.openapi.normalized.json": (
            {"available": pp["openapi_available"], **pp["openapi"]},
            [pp["openapi_fingerprint"]],
        ),
        "pp.success.observed.pruned.json": (
            {
                "endpoint_path": pp["endpoint_path"],
                "transport": pp["transport"],
                "wire_shape": pp["success_observation"],
                "alternatives": pp["alternatives"],
            },
            [pp["success_response_fingerprint"]]
            + [a["response_fingerprint"] for a in pp["alternatives"]],
        ),
        "pp.errors.observed.json": (
            pp["error_probes"],
            [p["response_fingerprint"] for p in pp["error_probes"]],
        ),
        "run.provenance.json": (
            {k: v for k, v in result.items() if k != "services"},
            sorted(fingerprints),
        ),
    }
    mock = result["execution_mode"] != "live"

    def artifact(observation: Any, sources: list[str]) -> dict[str, Any]:
        if not sources or not set(sources).issubset(fingerprints):
            raise ValueError("ARTIFACT_SOURCE_RESPONSE_MISMATCH")
        return {
            "fixture_kind": "synthetic_example" if mock else "sanitized_observed_wire",
            "contract_status": "synthetic" if mock else "verified",
            "generated_by": GENERATED_BY,
            "source_run_id": result["run_id"],
            "source_response_fingerprint": sources[0]
            if len(sources) == 1
            else compute_json_fingerprint(sources),
            "source_response_fingerprints": sources,
            "source_fingerprint_algorithm": "sha256_http_response_bytes_or_canonical_digest_list",
            "generated_at": result["completed_at"],
            "input_file_sha256": result["input_file_sha256"],
            "access_mode": ACCESS_MODE,
            "observation": observation,
        }

    generated = {name: artifact(value, sources) for name, (value, sources) in observations.items()}
    spec = {**artifact(None, sorted(fingerprints)), **result}
    spec.pop("observation", None)
    if mock:
        spec["overall_status"] = "SIMULATED_ACCEPTED"
        for service in spec["services"].values():
            service["contract_status"] = "synthetic"
    # Build/validate everything before writing any public artifact.
    specs_dir.mkdir(parents=True, exist_ok=True)
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    promoted: dict[str, list[str]] = {"specs": [], "fixtures": []}
    for name, value in generated.items():
        _write_json(fixtures_dir / name, value)
        promoted["fixtures"].append(name)
    _write_json(specs_dir / "discovered-model-contracts.json", spec)
    promoted["specs"].append("discovered-model-contracts.json")
    return promoted
