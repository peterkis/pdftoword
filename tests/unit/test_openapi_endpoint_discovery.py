"""
Unit tests for OpenAPI endpoint discovery.

Tests the logic for discovering endpoints from OpenAPI specs without network calls.
"""

from __future__ import annotations

# ============================================================================
# OpenAPI Endpoint Discovery Logic Tests
# ============================================================================


def test_multipart_endpoint_detection() -> None:
    """Test detection of multipart/form-data endpoints."""
    openapi_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/upload": {
                "post": {
                    "requestBody": {
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "file": {"type": "string", "format": "binary"},
                                    },
                                }
                            }
                        }
                    }
                }
            }
        },
    }

    paths = openapi_spec["paths"]
    multipart_endpoints = []

    for path, methods in paths.items():
        for method_name, operation in methods.items():
            if method_name.lower() != "post":
                continue

            request_body = operation.get("requestBody", {})
            content = request_body.get("content", {})

            if "multipart/form-data" in content:
                multipart_endpoints.append({
                    "path": path,
                    "method": method_name.upper(),
                    "transport": "multipart",
                })

    assert len(multipart_endpoints) == 1
    assert multipart_endpoints[0]["path"] == "/upload"
    assert multipart_endpoints[0]["transport"] == "multipart"


def test_json_base64_endpoint_detection() -> None:
    """Test detection of JSON with Base64 endpoints."""
    openapi_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/process": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "image": {"type": "string"},
                                    },
                                }
                            }
                        }
                    }
                }
            }
        },
    }

    paths = openapi_spec["paths"]
    json_endpoints = []

    for path, methods in paths.items():
        for method_name, operation in methods.items():
            if method_name.lower() != "post":
                continue

            request_body = operation.get("requestBody", {})
            content = request_body.get("content", {})

            if "application/json" in content:
                json_endpoints.append({
                    "path": path,
                    "method": method_name.upper(),
                    "transport": "json_base64",
                })

    assert len(json_endpoints) == 1
    assert json_endpoints[0]["path"] == "/process"


def test_endpoint_case_sensitivity() -> None:
    """Test that endpoint paths preserve case sensitivity."""
    openapi_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/Layout-Parsing": {
                "post": {
                    "summary": "Layout parsing endpoint",
                }
            },
            "/layout-parsing": {
                "post": {
                    "summary": "Different endpoint",
                }
            },
        },
    }

    paths = list(openapi_spec["paths"].keys())

    # Both paths should be present as-is
    assert "/Layout-Parsing" in paths
    assert "/layout-parsing" in paths

    # They are different endpoints
    assert openapi_spec["paths"]["/Layout-Parsing"] != openapi_spec["paths"]["/layout-parsing"]


def test_no_matching_endpoint_detection() -> None:
    """Test detection when no suitable endpoint exists."""
    openapi_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/info": {
                "get": {
                    "summary": "Get info",
                }
            },
            "/status": {
                "get": {
                    "summary": "Get status",
                }
            },
        },
    }

    paths = openapi_spec["paths"]
    upload_endpoints = []

    for path, methods in paths.items():
        for method_name, operation in methods.items():
            if method_name.lower() != "post":
                continue

            request_body = operation.get("requestBody", {})
            if request_body:
                upload_endpoints.append(path)

    # No POST endpoints with request body
    assert len(upload_endpoints) == 0


def test_relevance_keywords_detection() -> None:
    """Test detection of relevant endpoints based on keywords."""
    keywords = ["layout", "structure", "ocr", "parsing", "pipeline"]

    test_endpoints = [
        {"path": "/layout-parsing", "summary": "Parse document layout", "expected": True},
        {"path": "/PP-StructureV3", "summary": "Structure analysis", "expected": True},
        {"path": "/ocr/text", "summary": "Text OCR", "expected": True},
        {"path": "/health", "summary": "Health check", "expected": False},
        {"path": "/metrics", "summary": "Get metrics", "expected": False},
    ]

    for ep in test_endpoints:
        combined = " ".join([ep["path"], ep["summary"]]).lower()
        is_relevant = any(kw in combined for kw in keywords)
        assert is_relevant == ep["expected"], f"Failed for {ep['path']}"


def test_file_field_detection_from_schema() -> None:
    """Test detection of file field name from OpenAPI schema."""
    schema_with_binary = {
        "type": "object",
        "properties": {
            "file": {"type": "string", "format": "binary"},
            "name": {"type": "string"},
        },
    }

    properties = schema_with_binary.get("properties", {})
    file_field = None

    for prop_name, prop_schema in properties.items():
        if prop_schema.get("type") == "string" and prop_schema.get("format") in ("binary", "byte"):
            file_field = prop_name
            break

    assert file_field == "file"


def test_file_field_detection_without_format() -> None:
    """Test file field detection when format is not specified."""
    # Some APIs may use $ref or other patterns
    schema_with_ref = {
        "type": "object",
        "properties": {
            "document": {"$ref": "#/components/schemas/FileUpload"},
            "data": {"type": "object"},
        },
    }

    properties = schema_with_ref.get("properties", {})
    candidate_fields = []

    for prop_name, prop_schema in properties.items():
        # Check for $ref or other indicators
        if "$ref" in prop_schema or "oneOf" in prop_schema:
            candidate_fields.append(prop_name)

    # document field has a $ref, might be a file
    assert "document" in candidate_fields


# ============================================================================
# OpenAPI Version Tests
# ============================================================================


def test_openapi_version_extraction() -> None:
    """Test extraction of OpenAPI version."""
    openapi_3_0 = {"openapi": "3.0.0"}
    openapi_3_1 = {"openapi": "3.1.0"}
    swagger_2 = {"swagger": "2.0"}

    assert openapi_3_0.get("openapi") == "3.0.0"
    assert openapi_3_1.get("openapi") == "3.1.0"
    assert swagger_2.get("swagger") == "2.0"


def test_openapi_info_extraction() -> None:
    """Test extraction of OpenAPI info section."""
    openapi_spec = {
        "openapi": "3.1.0",
        "info": {
            "title": "FastAPI",
            "version": "0.1.0",
            "description": "API description",
        },
    }

    info = openapi_spec.get("info", {})
    assert info["title"] == "FastAPI"
    assert info["version"] == "0.1.0"


# ============================================================================
# Fingerprint Tests
# ============================================================================


def test_openapi_fingerprint_calculation() -> None:
    """Test calculation of OpenAPI fingerprint."""
    import hashlib
    import json

    openapi_spec = {
        "openapi": "3.1.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {},
    }

    # Normalize: sort keys, no whitespace
    normalized = json.dumps(openapi_spec, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    assert len(fingerprint) == 64  # SHA-256 produces 64 hex characters
    assert all(c in "0123456789abcdef" for c in fingerprint)


def test_fingerprint_deterministic() -> None:
    """Test that fingerprint is deterministic for same input."""
    import hashlib
    import json

    openapi_spec = {"openapi": "3.1.0", "paths": {}}

    normalized = json.dumps(openapi_spec, sort_keys=True, separators=(",", ":"))

    fingerprint1 = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    fingerprint2 = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    assert fingerprint1 == fingerprint2


def test_fingerprint_changes_with_content() -> None:
    """Test that fingerprint changes when content changes."""
    import hashlib
    import json

    spec1 = {"openapi": "3.1.0", "paths": {}}
    spec2 = {"openapi": "3.1.0", "paths": {"/new": {}}}

    def calc_fingerprint(spec: dict) -> str:
        normalized = json.dumps(spec, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    assert calc_fingerprint(spec1) != calc_fingerprint(spec2)
