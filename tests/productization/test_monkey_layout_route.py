"""Actual auto orchestration; replace only HTTP transport, never planning or parsing."""

from __future__ import annotations

import base64
import io
import json
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image
from prototypes.docx_output.common import PRIVATE, DemoError, digest, read, save
from prototypes.docx_output.pipeline import convert
from prototypes.docx_output.route_plan import execute_routes
from tests.productization.synthetic.generate import pdf_bytes
from tests.productization.test_auto_regions import mixed_pdf


@pytest.fixture
def case() -> Iterator[Path]:
    root = PRIVATE / ("monkey-layout-test-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root)


def prepare(case: Path, profile: str = "reconstruction-v2") -> tuple[Path, dict[str, Any]]:
    source = case / "source.pdf"
    mixed_pdf(source)
    job = convert(source, mode="auto", output_root=case / "jobs", auto_profile=profile)
    return job, read(job / "route-plan.json")


def stub(monkeypatch: pytest.MonkeyPatch, fault: str = "", cancel: Path | None = None) -> list[str]:
    calls: list[str] = []
    original = httpx.Client

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.port is not None
        provider = {8080: "pp", 9000: "monkey", 8000: "ovis"}[request.url.port]
        calls.append(provider)
        assert request.method == "POST"
        if provider == "monkey":
            if fault == "timeout":
                raise httpx.ReadTimeout("synthetic timeout")
            if fault == "http":
                return httpx.Response(503)
            return httpx.Response(
                200,
                json={
                    "model": "MonkeyOCRv2",
                    "choices": [
                        {
                            "finish_reason": "length" if fault == "length" else "stop",
                            "message": {
                                "content": "bad literal"
                                if fault == "malformed"
                                else '[{"label":"text","bbox":[10,20,500,200]}]'
                            },
                        }
                    ],
                },
            )
        if provider == "ovis":
            raise AssertionError("Figure or ambiguous single-text crop must not request Ovis")
        if cancel is not None:
            save(cancel / "route-cancelled.json", {"cancelled": True})
        if fault == "pp":
            return httpx.Response(503)
        data = json.loads(request.content)
        with Image.open(io.BytesIO(base64.b64decode(data["file"]))) as image:
            w, h = image.size
        return httpx.Response(
            200,
            json={
                "errorCode": 0,
                "errorMsg": "Success",
                "logId": "stub",
                "result": {
                    "dataInfo": {"width": w, "height": h},
                    "layoutParsingResults": [
                        {
                            "markdown": {"text": "", "isStart": True, "isEnd": True},
                            "prunedResult": {
                                "width": w,
                                "height": h,
                                "model_settings": {"use_doc_preprocessor": False},
                                "parsing_res_list": [
                                    {
                                        "block_label": "text" if fault == "ambiguous" else "image",
                                        "block_bbox": [0, 0, w, h],
                                        "block_content": "POISON",
                                    }
                                ],
                            },
                        }
                    ],
                },
            },
        )

    def client(*args: Any, **kwargs: Any) -> httpx.Client:
        return original(transport=httpx.MockTransport(handle))

    monkeypatch.setattr(httpx, "Client", client)
    return calls


def test_opt_in_plan_and_geometry_only_execution(
    case: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = stub(monkeypatch)
    job, plan = prepare(case)
    assert calls == [] and plan["request_budget"] == 3
    task = plan["layout_requests"][0]
    assert task["scope"] == "whole_visible_page" and task["provider_revision"] is None
    assert task["target"].endswith(":9000/v1/chat/completions")
    source_hash = digest(job / "auto.docx")
    before = read(job / "layout.prepared.json")["pages"][0]["blocks"]
    child = execute_routes(job, plan["plan_hash"], 3, True)
    assert calls == ["pp", "monkey"]
    ir = read(child / "layout.auto.json")
    assert ir["pages"][0]["blocks"] == before
    assert ir["metadata"]["content_provider"] == "ovis"
    candidates = ir["pages"][0]["geometry_candidates"]
    assert any(c["provider"] == "monkey" for c in candidates)
    assert ir["pages"][0]["selected_geometry_id"] is None
    assert digest(job / "auto.docx") == source_hash
    task = read(child / "layout-results.json")["tasks"][0]
    assert task["content_hash_before"] == task["content_hash_after"]
    assert task["status"] == "CANDIDATES_AVAILABLE"
    with pytest.raises(DemoError, match="ALREADY_ATTEMPTED"):
        execute_routes(job, plan["plan_hash"], 3, True)
    assert calls == ["pp", "monkey"]


@pytest.mark.parametrize("fault", ["timeout", "http", "length", "malformed", "pp", "ambiguous"])
def test_failures_and_figure_protection(
    case: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    calls = stub(monkeypatch, fault)
    job, plan = prepare(case)
    before = read(job / "layout.prepared.json")["pages"][0]["blocks"]
    child = execute_routes(job, plan["plan_hash"], 3, True)
    assert calls == ["pp", "monkey"]
    assert read(child / "layout.auto.json")["pages"][0]["blocks"] == before
    entries = read(child / "request-manifest.json")["requests"]
    assert len(entries) == 2 and entries[-1]["provider_revision"] is None
    if fault in {"timeout", "http", "length", "malformed"}:
        assert entries[-1]["status"] != "COMPLETE"
    else:
        assert read(child / "layout-results.json")["tasks"][0]["status"] == "CANDIDATES_AVAILABLE"


@pytest.mark.parametrize("fault", ["approval", "budget", "reviewed", "target", "input"])
def test_missing_or_changed_scope_never_sends(
    case: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    calls = stub(monkeypatch)
    job, plan = prepare(case)
    if fault == "reviewed":
        save(job / "layout.reviewed.json", {})
    if fault == "target":
        monkeypatch.setenv("MONKEY_BASE_URL", "http://localhost:9000")
    if fault == "input":
        (job / plan["layout_requests"][0]["image_path"]).write_bytes(b"changed")
    with pytest.raises(DemoError):
        execute_routes(job, plan["plan_hash"], 2 if fault == "budget" else 3, fault != "approval")
    assert calls == []


def test_cancel_stops_later_layout_and_records_it(
    case: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job, plan = prepare(case)
    calls = stub(monkeypatch, cancel=job)
    child = execute_routes(job, plan["plan_hash"], 3, True)
    assert calls == ["pp"]
    entries = read(child / "request-manifest.json")["requests"]
    assert entries[-1]["status"] == "CANCELLED" and not entries[-1]["http_attempted"]


def test_simple_native_zero_requests(case: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = stub(monkeypatch)
    source = case / "simple.pdf"
    source.write_bytes(pdf_bytes(b"BT /F1 14 Tf 30 340 Td (Native only) Tj ET"))
    job = convert(source, mode="auto", output_root=case / "jobs", auto_profile="reconstruction-v2")
    plan = read(job / "route-plan.json")
    assert plan["request_budget"] == 0 and plan["layout_requests"] == [] and calls == []


def test_legacy_approval_has_no_monkey_permission(
    case: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = stub(monkeypatch)
    job, plan = prepare(case, "legacy_ovis_pp")
    assert plan["layout_requests"] == [] and plan["request_budget"] == 2
    execute_routes(job, plan["plan_hash"], 2, True)
    assert calls == ["pp"]


def test_strict_replay_uses_same_orchestration_without_http(
    case: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = stub(monkeypatch)
    job, plan = prepare(case)
    first = execute_routes(job, plan["plan_hash"], 3, True)
    second = convert(
        job / "input.pdf", mode="auto", output_root=case / "jobs", auto_profile="reconstruction-v2"
    )
    plan2 = read(second / "route-plan.json")
    child = execute_routes(second, plan2["plan_hash"], 3, True, reuse_from=first, replay_only=True)
    assert calls == ["pp", "monkey"]
    manifest = read(child / "request-manifest.json")
    assert manifest["model_call_count"] == 0 and len(manifest["requests"]) == 2
    assert all(not r["http_attempted"] for r in manifest["requests"])
    assert read(child / "layout-results.json")["tasks"][0]["candidate_count"] == 1


def test_exhausted_budget_is_recorded_without_http(
    case: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prototypes.docx_output.layout_route import execute_layout

    job, plan = prepare(case)
    calls = stub(monkeypatch)
    ir = read(job / "layout.prepared.json")
    manifest = {
        "authorized": True,
        "model_call_count": 3,
        "budget": 3,
        "requests": [],
        "layout_permissions": plan["layout_requests"],
    }
    execute_layout(job, job, ir, plan["layout_requests"], manifest)
    assert calls == [] and manifest["requests"][0]["status"] == "REGION_BUDGET_EXCEEDED"


def test_missing_seal_does_not_fall_through_to_live(
    case: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = stub(monkeypatch)
    job, plan = prepare(case)
    first = execute_routes(job, plan["plan_hash"], 3, True)
    ledger = read(first / "request-manifest.json")
    ledger["requests"] = [r for r in ledger["requests"] if r["provider"] != "monkey"]
    save(first / "request-manifest.json", ledger)
    second = convert(
        job / "input.pdf", mode="auto", output_root=case / "jobs", auto_profile="reconstruction-v2"
    )
    plan2 = read(second / "route-plan.json")
    child = execute_routes(second, plan2["plan_hash"], 3, True, reuse_from=first, replay_only=True)
    assert calls == ["pp", "monkey"]
    result = read(child / "request-manifest.json")
    assert result["model_call_count"] == 0
    assert result["requests"][-1]["status"] == "SEALED_RESPONSE_UNAVAILABLE"


def test_api_exposes_distinct_page_scope(case: Path) -> None:
    from fastapi.testclient import TestClient
    from prototypes.docx_output.server import create_app

    job, plan = prepare(case)
    with TestClient(
        create_app(output_root=case / "jobs"), base_url="http://127.0.0.1:8765"
    ) as client:
        client.get("/api/session")
        response = client.get("/api/route/" + job.name)
        assert response.status_code == 200
        summary = response.json()
    assert summary["layout_requests"][0]["scope"] == "whole_visible_page"
    assert summary["plan_hash"] == plan["plan_hash"]
    assert summary["request_budget"] == 3
