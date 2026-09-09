#!/usr/bin/env python
"""
T0015 / P0-GATE-001A: Model Service Contract Discovery CLI

This is the CLI entry point that wraps the core discovery module.
The core logic is in scripts/model_contract_discovery.py for testability.

Usage:
    uv run python scripts/discover_model_contracts.py \
        --output-dir tmp/model-contract-discovery/<run-id> \
        --promote-artifacts

This tool:
- Reads real addresses and API keys ONLY from .env.local or environment variables
- Never writes secrets to Python code, Markdown, JSON fixtures, YAML, logs, or test output
- Saves raw responses to tmp/ directory (gitignored)
- When --promote-artifacts is set, generates sanitized fixtures to tests/fixtures/model_contracts/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Import core module
from model_contract_discovery import (
    DiscoveryConfig,
    HttpClient,
    ModelConfig,
    build_pp_error_probes,
    build_pp_json_payload,
    classify_monkey_content,
    compute_file_hash,
    compute_json_fingerprint,
    discover_pp_candidates_from_openapi,
    load_config,
    openai_endpoint_url,
    openapi_service_root,
    promote_sanitized_artifacts,
    redact_base64_images,
    redact_url,
    safe_parse_monkey_content,
    validate_monkey_block,
)


def main() -> int:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Discover model service contracts for T0015"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for discovery run",
    )
    parser.add_argument(
        "--test-image",
        type=Path,
        default=None,
        help="Test image for requests (default: scripts/test-page.jpg)",
    )
    parser.add_argument(
        "--promote-artifacts",
        action="store_true",
        help="Promote sanitized artifacts to specs/ and tests/fixtures/",
    )
    args = parser.parse_args()

    # Determine test image
    test_image = args.test_image or Path.cwd() / "scripts" / "test-page.jpg"

    if not test_image.exists():
        print(f"ERROR: Test image not found: {test_image}", file=sys.stderr)
        return 1

    # Load configuration
    config = load_config()

    # Validate configuration
    issues = []
    if not config.monkey.base_url:
        issues.append("MONKEY_OPENAI_BASE_URL not set")
    if not config.ovis.base_url:
        issues.append("OVIS_OPENAI_BASE_URL not set")
    if not config.pp.base_url:
        issues.append("PP_STRUCTURE_BASE_URL not set")

    if issues:
        print("ERROR: Missing configuration:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    # Create output directory
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = Path.cwd() / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Compute input file hash
    input_sha256 = compute_file_hash(test_image)
    print(f"Test image: {test_image}")
    print(f"Input SHA-256: {input_sha256[:16]}...")
    print()

    # Initialize HTTP client
    client = HttpClient(config.timeouts)

    try:
        results = run_full_discovery(
            client=client,
            config=config,
            output_dir=output_dir,
            test_image=test_image,
            input_sha256=input_sha256,
        )

        # Save results
        results_path = output_dir / "discovered-model-contracts.json"
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved: {results_path}")

        # Promote artifacts if requested
        if args.promote_artifacts and results.get("overall_status") == "ACCEPTED":
            specs_dir = Path.cwd() / "specs"
            fixtures_dir = Path.cwd() / "tests" / "fixtures" / "model_contracts"
            promoted = promote_sanitized_artifacts(output_dir, specs_dir, fixtures_dir)
            print("\nPromoted artifacts:")
            for category, files in promoted.items():
                if files:
                    print(f"  {category}: {len(files)} files")

        # Print summary
        print("\n" + "=" * 60)
        print("Discovery Complete")
        print("=" * 60)
        print(f"Overall Status: {results.get('overall_status', 'UNKNOWN')}")
        for service_name, service_result in results.get("services", {}).items():
            status = service_result.get("contract_status", "unknown")
            print(f"  {service_name}: {status}")

        return 0 if results.get("overall_status") == "ACCEPTED" else 1

    finally:
        client.close()


def run_full_discovery(
    client: HttpClient,
    config: DiscoveryConfig,
    output_dir: Path,
    test_image: Path,
    input_sha256: str,
) -> dict[str, Any]:
    """Run full discovery for all services."""
    import base64
    from datetime import UTC, datetime

    run_id = f"t0015-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    started_at = datetime.now(UTC).isoformat()

    # Read test image
    with open(test_image, "rb") as f:
        image_data = f.read()
    image_base64 = base64.b64encode(image_data).decode("utf-8")

    results: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "discovered_at": started_at,
        "input_file_sha256": input_sha256,
        "services": {},
    }

    # Discover Monkey
    print("=" * 60)
    print("Discovering MonkeyOCRv2...")
    print("=" * 60)
    monkey_result = discover_openai_service(
        client=client,
        config=config.monkey,
        output_dir=output_dir,
        image_base64=image_base64,
        service_name="monkey",
        expected_model_id="MonkeyOCRv2",
        prompt=(
            "Please output the categories and coordinates "
            "of the document elements in reading order."
        ),
    )
    results["services"]["monkey"] = monkey_result

    # Discover Ovis
    print("\n" + "=" * 60)
    print("Discovering OvisOCR2...")
    print("=" * 60)
    ovis_result = discover_openai_service(
        client=client,
        config=config.ovis,
        output_dir=output_dir,
        image_base64=image_base64,
        service_name="ovis",
        expected_model_id="ovis-ocr2",
        prompt=(
            "Extract the readable document content in reading order. "
            "Preserve original text, numbers, variables, units and symbols. "
            "Do not translate, correct, summarize or infer missing content."
        ),
    )
    results["services"]["ovis"] = ovis_result

    # Discover PP
    print("\n" + "=" * 60)
    print("Discovering PP-StructureV3...")
    print("=" * 60)
    pp_result = discover_pp_service(
        client=client,
        config=config.pp,
        output_dir=output_dir,
        image_base64=image_base64,
        image_data=image_data,  # Pass raw bytes for multipart
        candidate_paths=config.pp_candidate_paths,
        candidate_transports=config.pp_candidate_transports,
    )
    results["services"]["paddle"] = pp_result

    # Calculate overall status
    services = results.get("services", {})
    statuses = [s.get("contract_status", "unknown") for s in services.values()]

    if all(s == "verified" for s in statuses):
        results["overall_status"] = "ACCEPTED"
    elif "blocked_model_identity_mismatch" in statuses:
        results["overall_status"] = "BLOCKED_MODEL_IDENTITY_MISMATCH"
    elif "blocked_no_openapi" in statuses:
        results["overall_status"] = "BLOCKED_PP_CONTRACT_UNRESOLVED"
    else:
        results["overall_status"] = "BLOCKED"

    return results


def discover_openai_service(
    client: HttpClient,
    config: ModelConfig,
    output_dir: Path,
    image_base64: str,
    service_name: str,
    expected_model_id: str,
    prompt: str,
) -> dict[str, Any]:
    """Discover an OpenAI-compatible service."""
    result: dict[str, Any] = {
        "provider_type": "openai_compatible",
        "base_url_template": redact_url(config.base_url),
        "model_id": config.model,
        "models_path": "/v1/models",
        "chat_path": "/v1/chat/completions",
        "contract_status": "pending",
        "errors": [],
    }

    base_url = config.base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}

    # 1. Get models
    print("\n1. Fetching /v1/models...")
    models_url = openai_endpoint_url(base_url, "models")
    status, body, meta = client.get(models_url, headers=headers)

    # Save raw response
    raw_path = output_dir / f"{service_name}.models.raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(
            {"response": redact_base64_images(body), "metadata": meta.to_dict()},
            f,
            indent=2,
        )
    print(f"   Saved: {raw_path.name}")
    print(f"   Status: {status}, Duration: {meta.duration_ms}ms")

    if status != 200:
        print(f"   ERROR: HTTP {status}")
        result["errors"].append(f"models_endpoint_failed: {status}")
        result["contract_status"] = "blocked_models_endpoint"
        return result

    # Check model ID
    models = body.get("data", [])
    model_ids = [m.get("id", "") for m in models]
    print(f"   Found models: {model_ids}")

    if expected_model_id not in model_ids:
        print(f"   WARNING: Expected '{expected_model_id}' not found!")
        result["errors"].append(f"model_identity_mismatch: expected={expected_model_id}")
        result["contract_status"] = "blocked_model_identity_mismatch"
        result["actual_model_ids"] = model_ids
        return result

    result["actual_model_ids"] = model_ids

    # 2. Get OpenAPI
    print("\n2. Fetching OpenAPI spec...")
    service_root = openapi_service_root(base_url)
    openapi_url = f"{service_root}/openapi.json"
    status, body, meta = client.get(openapi_url)

    if status == 200 and "openapi" in body:
        raw_path = output_dir / f"{service_name}.openapi.raw.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(body, f, indent=2)
        print("   Found: /openapi.json")
        print(f"   Saved: {raw_path.name}")

        result["openapi_version"] = body.get("openapi", "unknown")
        result["openapi_fingerprint"] = compute_json_fingerprint(body)
        result["openapi_paths"] = list(body.get("paths", {}).keys())[:10]
    else:
        print("   OpenAPI not available")

    # 3. Test chat
    print("\n3. Testing chat completions...")
    chat_url = openai_endpoint_url(base_url, "chat/completions")
    chat_payload = {
        "model": expected_model_id,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ],
            }
        ],
        "max_tokens": 1000,
    }

    status, body, meta = client.post(chat_url, headers=headers, json_data=chat_payload)

    # Save redacted response
    redacted_body = redact_base64_images(body)
    raw_path = output_dir / f"{service_name}.chat.raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump({"response": redacted_body, "metadata": meta.to_dict()}, f, indent=2)
    print(f"   Saved: {raw_path.name}")
    print(f"   Status: {status}, Duration: {meta.duration_ms}ms")

    if status != 200:
        print(f"   ERROR: HTTP {status}")
        result["errors"].append(f"chat_endpoint_failed: {status}")
        result["contract_status"] = "blocked_chat_endpoint"
        return result

    # Analyze response
    choices = body.get("choices", [])
    if choices:
        message = choices[0].get("message", {})
        content = message.get("content")

        # Classify content (key fix for Monkey)
        classification = classify_monkey_content(content)
        print(f"   Wire type: {classification['wire_type']}")
        print(f"   Serialization: {classification['serialization']}")

        # If it's a Python literal, try to parse it safely
        if classification["wire_type"] == "string":
            try:
                parsed, _ = safe_parse_monkey_content(content)
                print(f"   Parsed to {len(parsed)} blocks")
                # Validate first block
                if parsed:
                    validation = validate_monkey_block(parsed[0], 800, 1159)
                    print(f"   Coordinate space: {validation.get('coordinate_space', 'unknown')}")
            except ValueError as e:
                print(f"   Parse error: {e}")

        result["wire_contract"] = classification
        result["finish_reason"] = choices[0].get("finish_reason")

    result["system_fingerprint"] = body.get("system_fingerprint")
    result["usage"] = body.get("usage", {})
    result["response_fingerprint"] = compute_json_fingerprint(redacted_body)
    result["contract_status"] = "verified"

    print(f"\n{service_name} contract verified!")
    return result


def discover_pp_service(
    client: HttpClient,
    config: ModelConfig,
    output_dir: Path,
    image_base64: str,
    image_data: bytes,
    candidate_paths: list[str],
    candidate_transports: list[str],
) -> dict[str, Any]:
    """Discover PP-StructureV3 service with bounded probe."""
    result: dict[str, Any] = {
        "provider_type": "paddle_pipeline",
        "base_url_template": redact_url(config.base_url),
        "endpoint_path": "",
        "method": "POST",
        "transport": "unknown",
        "file_field": "file",
        "file_type_field": "fileType",
        "contract_status": "pending",
        "errors": [],
        "probe_matrix": [],
    }

    base_url = config.base_url.rstrip("/")
    headers = {"Content-Type": "application/json"}

    # 1. Try OpenAPI first
    print("\n1. Checking for OpenAPI...")
    openapi_url = f"{base_url}/openapi.json"
    status, body, _meta = client.get(openapi_url)

    if status == 200 and "openapi" in body:
        print("   OpenAPI found!")
        raw_path = output_dir / "pp.openapi.raw.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(body, f, indent=2)

        result["openapi_available"] = True
        result["openapi_fingerprint"] = compute_json_fingerprint(body)

        # Discover candidates from OpenAPI
        candidates = discover_pp_candidates_from_openapi(body)
        if candidates:
            print(f"   Found {len(candidates)} candidates from OpenAPI")
            # Add to probe list
            for c in candidates:
                if c["path"] not in candidate_paths:
                    candidate_paths.append(c["path"])
                if c["transport"] not in candidate_transports:
                    candidate_transports.append(c["transport"])
    else:
        print("   OpenAPI not available")
        result["openapi_available"] = False

    # 2. Bounded runtime probe
    print("\n2. Running bounded probe matrix...")
    success_candidates = []

    for path in candidate_paths:
        for transport in candidate_transports:
            probe_result = probe_pp_candidate(
                client=client,
                base_url=base_url,
                path=path,
                transport=transport,
                image_base64=image_base64,
                image_data=image_data,
                headers=headers,
            )
            result["probe_matrix"].append(probe_result)

            status_str = "SUCCESS" if probe_result["success"] else "FAILED"
            print(f"   {path} + {transport}: {status_str} ({probe_result['http_status']})")

            if probe_result["success"]:
                success_candidates.append(probe_result)

    # Save probe results
    raw_path = output_dir / "pp.probe-matrix.raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(redact_base64_images(result["probe_matrix"]), f, indent=2)
    print(f"\n   Saved: {raw_path.name}")

    # 3. Select primary candidate
    if success_candidates:
        primary = success_candidates[0]
        result["endpoint_path"] = primary["path"]
        result["transport"] = primary["transport"]
        result["contract_source"] = "bounded_runtime_probe"

        # Save success response
        raw_path = output_dir / "pp.success.raw.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(redact_base64_images(primary.get("response", {})), f, indent=2)

        if len(success_candidates) > 1:
            result["alternatives"] = [
                {"path": c["path"], "transport": c["transport"]}
                for c in success_candidates[1:]
            ]
            result["selection_reason"] = "first_successful_candidate"

        # 4. Test error probes
        print("\n3. Testing error responses...")
        error_probes = build_pp_error_probes()
        error_results = []

        for probe in error_probes:
            url = f"{base_url}{primary['path']}"
            # Use valid base64 for tests
            if "valid_base64" in str(probe["payload"].get("file", "")):
                probe["payload"]["file"] = image_base64[:100]

            status, body, _meta = client.post(url, headers=headers, json_data=probe["payload"])
            error_results.append({
                "name": probe["name"],
                "http_status": status,
                "error_code": body.get("errorCode") if isinstance(body, dict) else None,
            })
            print(f"   {probe['name']}: HTTP {status}")

        result["error_probes"] = error_results

        # Save error results
        raw_path = output_dir / "pp.errors.raw.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(error_results, f, indent=2)

        result["contract_status"] = "verified"
        result["submodel_endpoint_enumeration"] = "unknown"
        result["submodel_endpoint_reason"] = "openapi_not_exposed_and_probe_scope_limited"
        print("\nPP contract verified!")

    else:
        print("\n   No candidate succeeded")
        result["contract_status"] = "blocked_no_openapi"
        result["errors"].append("all_probe_candidates_failed")

    return result


def probe_pp_candidate(
    client: HttpClient,
    base_url: str,
    path: str,
    transport: str,
    image_base64: str,
    image_data: bytes,
    headers: dict[str, str],
) -> dict[str, Any]:
    """Probe a single PP candidate."""
    url = f"{base_url}{path}"
    probe_result: dict[str, Any] = {
        "path": path,
        "transport": transport,
        "success": False,
        "http_status": 0,
    }

    if transport == "multipart":
        # Multipart form upload (preferred for PP-StructureV3)
        # Use multipart/form-data with file field
        files = {"file": ("test.jpg", image_data, "image/jpeg")}
        # Remove Content-Type header for multipart (httpx sets it automatically)
        multipart_headers = {k: v for k, v in headers.items() if k.lower() != "content-type"}
        status, body, meta = client.post(url, headers=multipart_headers, files=files)
        probe_result["http_status"] = status
        probe_result["duration_ms"] = meta.duration_ms
        probe_result["response_fingerprint"] = compute_json_fingerprint(body)[:16]

        if (
            status == 200
            and isinstance(body, dict)
            and body.get("errorCode") == 0
            and "result" in body
        ):
            probe_result["success"] = True
            probe_result["response"] = body

    elif transport == "json_base64":
        # JSON with base64-encoded file
        payload = build_pp_json_payload(image_base64, file_type=1)
        status, body, meta = client.post(url, headers=headers, json_data=payload)
        probe_result["http_status"] = status
        probe_result["duration_ms"] = meta.duration_ms
        probe_result["response_fingerprint"] = compute_json_fingerprint(body)[:16]

        if (
            status == 200
            and isinstance(body, dict)
            and body.get("errorCode") == 0
            and "result" in body
        ):
            probe_result["success"] = True
            probe_result["response"] = body

    return probe_result


if __name__ == "__main__":
    sys.exit(main())
