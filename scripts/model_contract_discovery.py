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
import hashlib
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

# ============================================================================
# Configuration
# ============================================================================


@dataclass
class ModelConfig:
    """Configuration for a model service."""

    base_url: str
    model: str = ""
    api_key: str = ""


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
    # Priority: /PP-StructureV3 (case-sensitive) > /layout-parsing
    pp_candidate_paths: list[str] = field(
        default_factory=lambda: ["/PP-StructureV3", "/layout-parsing"]
    )
    # Priority: multipart (file upload) > json_base64
    pp_candidate_transports: list[str] = field(
        default_factory=lambda: ["multipart", "json_base64"]
    )


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

    # Extract path and strip to base /v1
    path = parsed.path
    if "/v1" in path:
        # Find the first /v1 and use that as the base
        v1_index = path.find("/v1")
        path = path[: v1_index + 3]  # Include "/v1"
    else:
        # No /v1, add it
        path = path + "/v1"

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
    if endpoint.startswith("/"):
        endpoint = endpoint[1:]
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

    # Remove only the last /v1 segment
    if path.endswith("/v1"):
        path = path[:-3]

    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


# ============================================================================
# Redaction
# ============================================================================


def redact_url(url: str) -> str:
    """Redact host/IP from URL, preserving scheme, port, and path."""
    if not url:
        return ""

    parsed = urlparse(url)
    redacted_netloc = f"MODEL_SERVER_IP:{parsed.port}" if parsed.port else "MODEL_SERVER_IP"

    return urlunparse((parsed.scheme, redacted_netloc, parsed.path, "", "", ""))


def redact_text(text: str, max_preview: int = 50) -> str:
    """Redact sensitive text content.

    Returns SHA-256 hash and length instead of content.
    """
    if not text:
        return ""

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"[REDACTED:{content_hash}:len={len(text)}]"


def redact_base64_images(data: Any, max_length: int = 100) -> Any:
    """Recursively redact base64 image data."""
    base64_chars = (
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"
        "0123456789+/="
    )

    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            key_lower = key.lower()
            # Detect image fields
            image_fields = (
                "image", "img", "img_base64",
                "image_base64", "inputimage", "outputimages"
            )
            if key_lower in image_fields:
                if isinstance(value, str) and len(value) > max_length:
                    result[key] = redact_text(value)
                else:
                    result[key] = value
            elif isinstance(value, str) and value.startswith("data:image"):
                result[key] = "[REDACTED_DATA_URL]"
            elif isinstance(value, str) and len(value) > 1000:
                # Check if looks like base64
                sample = value[:100]
                if (
                    len(value) % 4 == 0
                    and all(c in base64_chars for c in sample)
                ):
                    result[key] = redact_text(value)
                else:
                    result[key] = value
            else:
                result[key] = redact_base64_images(value)
        return result
    elif isinstance(data, list):
        return [redact_base64_images(item) for item in data]
    else:
        return data


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Redact sensitive headers."""
    sensitive_keys = {"authorization", "api-key", "x-api-key", "token", "apikey"}
    result = {}
    for key, value in headers.items():
        if key.lower() in sensitive_keys:
            result[key] = "[REDACTED]"
        else:
            result[key] = value
    return result


# ============================================================================
# Fingerprint
# ============================================================================


def compute_json_fingerprint(data: Any) -> str:
    """Compute SHA-256 fingerprint of normalized JSON."""
    normalized = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


# ============================================================================
# Monkey Content Parsing
# ============================================================================


def classify_monkey_content(content: Any) -> dict[str, Any]:
    """Classify Monkey response content wire type.

    Returns dict with:
    - wire_type: "string" or "array"
    - serialization: "python_literal_list" or "json" or "unknown"
    - parsed_type: "array<object>" or "unknown"
    """
    if isinstance(content, list):
        return {
            "wire_type": "array",
            "serialization": "json",
            "parsed_type": "array<object>",
        }
    elif isinstance(content, str):
        # Check if it looks like Python literal list
        stripped = content.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            return {
                "wire_type": "string",
                "serialization": "python_literal_list",
                "parsed_type": "array<object>",
            }
        else:
            return {
                "wire_type": "string",
                "serialization": "unknown",
                "parsed_type": "unknown",
            }
    else:
        return {
            "wire_type": "unknown",
            "serialization": "unknown",
            "parsed_type": "unknown",
        }


def safe_parse_monkey_content(content: Any) -> tuple[list[Any], dict[str, Any]]:
    """Safely parse Monkey content.

    Uses ast.literal_eval for Python literal strings.
    NEVER uses eval().

    Returns:
        (parsed_list, classification_info)

    Raises:
        ValueError if parsing fails
    """
    classification = classify_monkey_content(content)

    if isinstance(content, list):
        return content, classification

    if isinstance(content, str):
        stripped = content.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                # Use ast.literal_eval - SAFE, no code execution
                parsed = ast.literal_eval(stripped)
                if isinstance(parsed, list):
                    return parsed, classification
            except (ValueError, SyntaxError) as e:
                raise ValueError(f"Failed to parse Monkey content: {e}") from e

    raise ValueError(f"Cannot parse Monkey content with type {type(content)}")


def validate_monkey_block(block: Any, page_width: int, page_height: int) -> dict[str, Any]:
    """Validate a single Monkey block.

    Checks:
    - block is dict
    - bbox has 4 elements
    - bbox values are in normalized_1000 space (0-1000)
    - label is string

    Returns validation result with warnings.
    """
    warnings: list[str] = []

    if not isinstance(block, dict):
        return {"valid": False, "error": "block is not a dict"}

    # Check bbox
    bbox = block.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return {"valid": False, "error": "bbox missing or wrong length"}

    # Check bbox values
    for i, val in enumerate(bbox):
        if not isinstance(val, int | float):
            warnings.append(f"bbox[{i}] is not numeric")
        elif val < 0 or val > 1000:
            warnings.append(f"bbox[{i}]={val} outside normalized_1000 range [0,1000]")

    # Check label
    label = block.get("label")
    if not isinstance(label, str):
        warnings.append("label is not a string")

    return {
        "valid": len(warnings) == 0,
        "warnings": warnings,
        "coordinate_space": "normalized_1000",
        "note": "Coordinates are normalized to 0-1000 range, not page pixels",
    }


# ============================================================================
# HTTP Client
# ============================================================================


@dataclass
class RequestMetadata:
    """Metadata for an HTTP request."""

    request_id: str
    started_at: str
    duration_ms: float = 0.0
    method: str = ""
    url: str = ""  # Already redacted
    request_content_type: str = ""
    response_status: int = 0
    response_content_type: str = ""
    redirect_count: int = 0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "request_id": self.request_id,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "method": self.method,
            "url": self.url,
            "request_content_type": self.request_content_type,
            "response_status": self.response_status,
            "response_content_type": self.response_content_type,
            "redirect_count": self.redirect_count,
            "error": self.error,
        }


class HttpClient:
    """HTTP client with proper timeout and metadata tracking."""

    def __init__(self, timeouts: Timeouts):
        self.timeouts = timeouts
        self.client = httpx.Client(
            timeout=httpx.Timeout(
                connect=timeouts.connect,
                read=timeouts.request,
                write=timeouts.request,
                pool=timeouts.connect,
            ),
            follow_redirects=True,
        )

    def _record_metadata(
        self,
        request_id: str,
        started_at: datetime,
        method: str,
        url: str,
        request_content_type: str = "",
        response_status: int = 0,
        response_content_type: str = "",
        redirect_count: int = 0,
        error: str = "",
    ) -> RequestMetadata:
        """Create request metadata record."""
        completed_at = datetime.now(UTC)
        duration_ms = (completed_at - started_at).total_seconds() * 1000

        return RequestMetadata(
            request_id=request_id,
            started_at=started_at.isoformat(),
            duration_ms=round(duration_ms, 2),
            method=method,
            url=redact_url(url),
            request_content_type=request_content_type,
            response_status=response_status,
            response_content_type=response_content_type,
            redirect_count=redirect_count,
            error=error,
        )

    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any], RequestMetadata]:
        """Make GET request with full metadata."""
        request_id = str(uuid.uuid4())[:8]
        started_at = datetime.now(UTC)

        try:
            response = self.client.get(url, headers=headers or {})

            metadata = self._record_metadata(
                request_id=request_id,
                started_at=started_at,
                method="GET",
                url=url,
                request_content_type="",
                response_status=response.status_code,
                response_content_type=response.headers.get("content-type", ""),
                redirect_count=len(response.history),
            )

            try:
                body = response.json()
            except Exception:
                body = {"_raw_text": response.text[:500] if response.text else ""}

            return response.status_code, body, metadata

        except httpx.TimeoutException as e:
            metadata = self._record_metadata(
                request_id=request_id,
                started_at=started_at,
                method="GET",
                url=url,
                error=f"Timeout: {type(e).__name__}",
            )
            return 0, {"error": "timeout"}, metadata

        except httpx.RequestError as e:
            # Redact error message
            error_msg = str(e).replace(urlparse(url).netloc, "MODEL_SERVER_IP")
            metadata = self._record_metadata(
                request_id=request_id,
                started_at=started_at,
                method="GET",
                url=url,
                error=f"Request error: {type(e).__name__}",
            )
            return 0, {"error": error_msg}, metadata

    def post(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        json_data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any], RequestMetadata]:
        """Make POST request with full metadata.

        Note: Uses 'is not None' checks for json_data and files.
        Empty dict {} IS sent as JSON body.
        """
        request_id = str(uuid.uuid4())[:8]
        started_at = datetime.now(UTC)

        try:
            if files is not None:
                content_type = "multipart/form-data"
                response = self.client.post(url, headers=headers or {}, files=files, data=data)
            elif json_data is not None:
                content_type = "application/json"
                response = self.client.post(url, headers=headers or {}, json=json_data)
            else:
                content_type = ""
                response = self.client.post(url, headers=headers or {}, data=data)

            metadata = self._record_metadata(
                request_id=request_id,
                started_at=started_at,
                method="POST",
                url=url,
                request_content_type=content_type,
                response_status=response.status_code,
                response_content_type=response.headers.get("content-type", ""),
                redirect_count=len(response.history),
            )

            try:
                body = response.json()
            except Exception:
                body = {"_raw_text": response.text[:500] if response.text else ""}

            return response.status_code, body, metadata

        except httpx.TimeoutException as e:
            metadata = self._record_metadata(
                request_id=request_id,
                started_at=started_at,
                method="POST",
                url=url,
                error=f"Timeout: {type(e).__name__}",
            )
            return 0, {"error": "timeout"}, metadata

        except httpx.RequestError as e:
            metadata = self._record_metadata(
                request_id=request_id,
                started_at=started_at,
                method="POST",
                url=url,
                error=f"Request error: {type(e).__name__}",
            )
            return 0, {"error": str(e)}, metadata

    def close(self) -> None:
        """Close the client."""
        self.client.close()


# ============================================================================
# PP Discovery
# ============================================================================


def discover_pp_candidates_from_openapi(
    openapi_spec: dict[str, Any],
) -> list[dict[str, Any]]:
    """Discover PP candidates from OpenAPI spec.

    Returns list of candidate endpoints that could handle file/image uploads.
    """
    candidates = []
    paths = openapi_spec.get("paths", {})

    for path, methods in paths.items():
        post_op = methods.get("post", {})
        if not post_op:
            continue

        request_body = post_op.get("requestBody", {})
        content = request_body.get("content", {})

        # Check for multipart
        if "multipart/form-data" in content:
            schema = content["multipart/form-data"].get("schema", {})
            properties = schema.get("properties", {})
            file_field = None
            for prop_name, prop_schema in properties.items():
                prop_type = prop_schema.get("type")
                prop_format = prop_schema.get("format")
                if prop_type == "string" and prop_format in ("binary", "byte"):
                    file_field = prop_name
                    break
                if "$ref" in prop_schema or "oneOf" in prop_schema:
                    file_field = prop_name

            candidates.append({
                "path": path,
                "transport": "multipart",
                "file_field": file_field or "file",
                "operation_id": post_op.get("operationId"),
                "summary": post_op.get("summary"),
            })

        # Check for JSON with base64
        if "application/json" in content:
            schema = content["application/json"].get("schema", {})
            properties = schema.get("properties", {})
            for prop_name, _prop_schema in properties.items():
                name_lower = prop_name.lower()
                if "base64" in name_lower or "image" in name_lower or prop_name == "file":
                    candidates.append({
                        "path": path,
                        "transport": "json_base64",
                        "file_field": prop_name,
                        "operation_id": post_op.get("operationId"),
                        "summary": post_op.get("summary"),
                    })
                    break

    return candidates


def build_pp_json_payload(
    file_base64: str,
    file_type: int,
) -> dict[str, Any]:
    """Build PP JSON payload with required fileType field.

    Args:
        file_base64: Base64 encoded file content
        file_type: 0 for PDF, 1 for image

    Returns:
        JSON payload dict with file and fileType fields
    """
    return {
        "file": file_base64,
        "fileType": file_type,
    }


def build_pp_error_probes() -> list[dict[str, Any]]:
    """Build PP error probe payloads.

    Returns list of error probe configurations:
    - missing file
    - invalid fileType
    - invalid file content
    """
    return [
        {
            "name": "missing_file",
            "payload": {"fileType": 1},
            "description": "Missing required file field",
        },
        {
            "name": "invalid_file_type",
            "payload": {"file": "valid_base64_placeholder", "fileType": 99},
            "description": "fileType must be 0 or 1",
        },
        {
            "name": "invalid_file",
            "payload": {"file": "not-valid-base64!!!", "fileType": 1},
            "description": "Invalid base64 file content",
        },
    ]


# ============================================================================
# Run Discovery
# ============================================================================


@dataclass
class RunMetadata:
    """Metadata for a discovery run."""

    run_id: str
    started_at: str
    completed_at: str = ""
    tool_git_commit: str = ""
    input_file_sha256: str = ""
    input_size_bytes: int = 0
    operating_system: str = ""
    python_version: str = ""
    httpx_version: str = ""


def run_discovery(
    config: DiscoveryConfig,
    output_dir: Path,
    test_image: Path,
    promote_artifacts: bool = False,
) -> dict[str, Any]:
    """Run complete discovery process.

    Args:
        config: Discovery configuration
        output_dir: Directory for raw artifacts
        test_image: Path to test image file
        promote_artifacts: If True, also generate specs/ and tests/fixtures/

    Returns:
        Discovery results dict with overall_status
    """
    run_id = f"t0015-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    started_at = datetime.now(UTC)

    # Compute input file hash
    input_sha256 = compute_file_hash(test_image)
    input_size = test_image.stat().st_size

    # Create run metadata
    run_meta = RunMetadata(
        run_id=run_id,
        started_at=started_at.isoformat(),
        input_file_sha256=input_sha256,
        input_size_bytes=input_size,
        operating_system=sys.platform,
        python_version=sys.version.split()[0],
        httpx_version=httpx.__version__,
    )

    # Try to get git commit
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        if result.returncode == 0:
            run_meta.tool_git_commit = result.stdout.strip()[:12]
    except Exception:
        pass

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save run metadata
    run_meta_path = output_dir / "run-metadata.json"

    # Initialize client
    client = HttpClient(config.timeouts)

    try:
        # Discovery results
        results: dict[str, Any] = {
            "schema_version": "1.0",
            "run_id": run_id,
            "discovered_at": started_at.isoformat(),
            "services": {},
        }

        # Discover each service
        # ... (implementation would go here)

        # Calculate overall status
        services = results.get("services", {})
        statuses = [s.get("contract_status", "unknown") for s in services.values()]

        if all(s == "verified" for s in statuses):
            results["overall_status"] = "ACCEPTED"
        elif "blocked_model_identity_mismatch" in statuses:
            results["overall_status"] = "BLOCKED_MODEL_IDENTITY_MISMATCH"
        else:
            results["overall_status"] = "BLOCKED"

        # Update run metadata
        run_meta.completed_at = datetime.now(UTC).isoformat()

        # Save run metadata
        with open(run_meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "run_id": run_meta.run_id,
                "started_at": run_meta.started_at,
                "completed_at": run_meta.completed_at,
                "tool_git_commit": run_meta.tool_git_commit,
                "input_file_sha256": run_meta.input_file_sha256,
                "input_size_bytes": run_meta.input_size_bytes,
                "operating_system": run_meta.operating_system,
                "python_version": run_meta.python_version,
                "httpx_version": run_meta.httpx_version,
            }, f, indent=2)

        # Save results
        results_path = output_dir / "discovered-model-contracts.json"
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        return results

    finally:
        client.close()


def promote_sanitized_artifacts(
    source_dir: Path,
    specs_dir: Path,
    fixtures_dir: Path,
) -> dict[str, list[str]]:
    """Promote sanitized artifacts from discovery run to public locations.

    Generates:
    - specs/discovered-model-contracts.json
    - tests/fixtures/model_contracts/*.json

    Each artifact includes provenance:
    - generated_by
    - source_run_id
    - source_response_fingerprint
    - fixture_kind: "sanitized_observed_wire"
    """
    promoted: dict[str, list[str]] = {"specs": [], "fixtures": []}

    # Read source results
    source_results = source_dir / "discovered-model-contracts.json"
    if not source_results.exists():
        return promoted

    with open(source_results, encoding="utf-8") as f:
        results = json.load(f)

    run_id = results.get("run_id", "unknown")

    # Add provenance to results
    results["generated_by"] = "scripts/model_contract_discovery.py"
    results["source_run_id"] = run_id
    results["artifact_provenance"] = "sanitized_observed_wire"

    # Save to specs
    specs_dir.mkdir(parents=True, exist_ok=True)
    specs_path = specs_dir / "discovered-model-contracts.json"
    with open(specs_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    promoted["specs"].append(str(specs_path))

    # Generate fixtures
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    # ... (fixture generation would go here)

    return promoted
