"""OpenAPI extraction tests call only the production discovery functions."""

from __future__ import annotations

from typing import Any

import pytest

from model_contract_discovery import (
    compute_json_fingerprint,
    discover_pp_candidates_from_openapi,
    normalize_openapi,
    openapi_service_root,
    resolve_refs,
)


def document(
    media: str = "application/json", path: str = "/layout-parsing", file_field: str = "file"
) -> dict[str, Any]:
    """An explicitly synthetic OpenAPI example with schemas and query parameters."""
    return {
        "openapi": "3.1.0",
        "info": {"title": "Test API", "version": "test-version"},
        "servers": [{"url": "http://server.invalid"}],
        "paths": {
            path: {
                "post": {
                    "operationId": "parse_document",
                    "parameters": [
                        {
                            "name": "mode",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string"},
                        },
                    ],
                    "requestBody": {
                        "content": {
                            media: {
                                "schema": {
                                    "$ref": "#/components/schemas/Input",
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"errorMsg": {"type": "string"}},
                                    }
                                }
                            }
                        },
                        "422": {"description": "validation error"},
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "Input": {
                    "type": "object",
                    "required": [file_field, "fileType"],
                    "properties": {
                        file_field: {"type": "string", "format": "binary"},
                        "fileType": {"type": "integer", "enum": [0, 1]},
                    },
                }
            }
        },
    }


@pytest.mark.parametrize(
    "media,transport",
    [
        ("application/json", "json_base64"),
        ("multipart/form-data", "multipart"),
    ],
)
def test_endpoint_and_schema_extraction(media: str, transport: str) -> None:
    """Resolved refs retain exact fields, required list, responses and query schemas."""
    candidates = discover_pp_candidates_from_openapi(document(media))
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["transport"] == transport
    assert candidate["method"] == "POST"
    assert candidate["required"] == ["file", "fileType"]
    assert candidate["operation_id"] == "parse_document"
    assert candidate["query_parameters"][0]["name"] == "mode"
    assert candidate["responses"]["200"]["content"]["application/json"]["schema"]["properties"][
        "errorMsg"
    ] == {"type": "string"}
    assert "422" in candidate["responses"]


@pytest.mark.parametrize("path", ["/layout-parsing", "/PP-StructureV3", "/Layout-Parsing"])
def test_exact_case_preserved(path: str) -> None:
    """Endpoint paths are never lowercased."""
    assert discover_pp_candidates_from_openapi(document(path=path))[0]["path"] == path


def test_multipart_field_from_ref() -> None:
    """Nonstandard multipart field names are resolved from the actual Schema."""
    candidate = discover_pp_candidates_from_openapi(
        document("multipart/form-data", file_field="document")
    )[0]
    assert candidate["file_field"] == "document"


def test_no_upload_candidate() -> None:
    """GET-only documents do not create a made-up POST candidate."""
    assert discover_pp_candidates_from_openapi({"paths": {"/health": {"get": {}}}}) == []


def test_unresolved_ref_is_incomplete() -> None:
    """Missing references are explicit incomplete discovery, never guessed fields."""
    data = document()
    data["components"] = {}
    assert normalize_openapi(data)["incomplete"]
    assert discover_pp_candidates_from_openapi(data) == []


def test_external_ref_never_fetches_network() -> None:
    """External refs are not dereferenced by the discovery tool."""
    with pytest.raises(ValueError, match="UNRESOLVED"):
        resolve_refs({"$ref": "http://server.invalid/schema"}, {})


def test_cyclic_ref_is_bounded() -> None:
    """Recursive schema cycles do not trigger unbounded recursion."""
    data: dict[str, Any] = {"a": {"$ref": "#/a"}}
    with pytest.raises(ValueError, match="UNRESOLVED"):
        resolve_refs(data["a"], data)


def test_info_version_and_server_removal() -> None:
    """Metadata is retained while OpenAPI server hosts cannot alter runtime URLs."""
    normalized = normalize_openapi(document())
    assert normalized["openapi_version"] == "3.1.0"
    assert normalized["info"] == {"title": "Test API", "version": "test-version"}
    assert "servers" not in normalized


@pytest.mark.parametrize(
    "url,expected",
    [
        ("http://host:9000", "http://host:9000"),
        ("http://host:9000/v1", "http://host:9000"),
        ("http://host:9000/api/v1", "http://host:9000/api"),
        ("", ""),
    ],
)
def test_openapi_root(url: str, expected: str) -> None:
    """Remove only the trailing API version segment for service discovery."""
    assert openapi_service_root(url) == expected


def test_fingerprint_changes_with_schema() -> None:
    """A changed Schema must invalidate the prior OpenAPI fingerprint."""
    assert compute_json_fingerprint(document()) != compute_json_fingerprint(
        document("multipart/form-data")
    )
