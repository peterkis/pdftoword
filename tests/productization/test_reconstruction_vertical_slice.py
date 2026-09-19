"""Actual shared export chain and source ranges; synthetic evidence is not real adoption."""

from __future__ import annotations

import copy
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn
from prototypes.docx_output.common import PRIVATE, DemoError, Json, new_job, read, save
from prototypes.docx_output.geometry.candidate import full_page, record
from prototypes.docx_output.pipeline import finish
from prototypes.docx_output.renderers.legacy import LegacyRenderer
from tests.productization.test_monkey_layout_route import prepare, stub
from tests.productization.test_shared_structure_actual import text_ir


@pytest.fixture
def case() -> Iterator[Path]:
    root = PRIVATE / ("vertical-test-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root)


def document(case: Path) -> tuple[Path, Json]:
    ir = text_ir(case, "Synthetic source")
    job = new_job(case / "jobs")
    page = ir["pages"][0]
    page["blocks"][0]["type"] = "paragraph"
    info = ir["provenance"]["pages"]["0"]
    for index, provider in enumerate(("monkey", "pp")):
        p = copy.deepcopy(page)
        p["page_index"] = index
        b = p["blocks"][0]
        b.update(id=f"source-{index}", page_index=index)
        p["reading_order"] = [b["id"]]
        candidate = record(
            provider,
            index,
            0,
            "text",
            "region",
            "semantic_region",
            [v / info["pixel_to_point"][0] for v in [9, 9, 301, 51]],
            "input_pixel",
            full_page(p, info),
            {},
        )
        p["geometry_candidates"] = [candidate]
        if index == 0:
            ir["pages"][0] = p
        else:
            ir["pages"].append(p)
        ir["provenance"]["pages"][str(index)] = copy.deepcopy(info)
    save(job / "route-plan.json", {"profile": "reconstruction-v2"})
    return job, ir


def test_page_specific_selection_reaches_plan_docx_and_ranges(case: Path) -> None:
    job, ir = document(case)
    before = copy.deepcopy(ir)
    qa = finish(job, ir)
    assert ir == before
    assert [p["selected_geometry_provider"] for p in qa["pages"]] == ["monkey", "pp"]
    assert all(p["renderer"] == "flow" for p in qa["pages"])
    planned = read(job / "render-plan.auto.json")
    assert planned["schema_version"] == "render-plan/2"
    records = read(job / "source-map.auto.json")["blocks"]
    doc = Document(str(job / "auto.docx"))
    for entry in records:
        start = next(
            s
            for s in doc.element.body.xpath(".//w:bookmarkStart")
            if s.get(qn("w:name")) == entry["marker"]
        )
        end = next(
            e
            for e in doc.element.body.xpath(".//w:bookmarkEnd")
            if e.get(qn("w:id")) == start.get(qn("w:id"))
        )
        siblings = list(start.getparent())
        payload = siblings[siblings.index(start) + 1 : siblings.index(end)]
        assert (
            "".join(t.text or "" for el in payload for t in el.iter(qn("w:t")))
            == "Synthetic source"
        )
    assert qa["visual_review_status"] == "PENDING"
    assert (
        read(job / "reconstruction-execution.auto.json")["structure_status"]
        == "EXECUTED_PUBLIC_API"
    )


def test_reviewed_export_never_reprocesses_or_changes_geometry(case: Path) -> None:
    job, ir = document(case)
    finish(job, ir)
    selected = read(job / "layout.auto.json")
    old = copy.deepcopy(selected["pages"])
    selected["pages"][0]["blocks"][0]["content"]["plain_text"] = "Human edited source"
    finish(job, selected, "reviewed")
    result = read(job / "layout.reviewed.json")
    assert result["pages"][0]["blocks"][0]["content"]["plain_text"] == "Human edited source"
    assert result["pages"][0]["blocks"][0]["bbox"] == old[0]["blocks"][0]["bbox"]
    assert (
        read(job / "reconstruction-execution.reviewed.json")["structure_status"]
        == "REUSED_FINALIZED"
    )
    assert read(job / "layout.auto.json")["pages"] == old


def test_invalid_page_isolated_and_renderer_capability_fallback(case: Path) -> None:
    job, ir = document(case)
    save(
        job / "request-manifest.json",
        {
            "requests": [
                {
                    "provider": "pp",
                    "page_index": 0,
                    "status": "COMPLETE",
                    "input_sha256": "missing-source",
                    "region_id": "missing-evidence",
                }
            ]
        },
    )
    qa = finish(job, ir, renderer=LegacyRenderer())
    assert qa["pages"][0]["layout_status"] == "ABSTAIN"
    assert qa["pages"][1]["selected_geometry_provider"] == "pp"
    result = read(job / "layout.auto.json")
    assert result["metadata"]["reconstruction"]["renderer_fallback"]["requested"] == "legacy"
    assert read(job / "render-manifest.auto.json")["renderer"]["name"] == "flow"


def test_auto_reexport_stale_stage_rejected(case: Path) -> None:
    job, ir = document(case)
    finish(job, ir)
    selected = read(job / "layout.auto.json")
    selected["pages"][0]["blocks"][0]["content"]["plain_text"] = "Unapproved stale value"
    with pytest.raises(DemoError, match="RECONSTRUCTION_STAGE_STALE"):
        finish(new_job(case / "other"), selected)


def test_actual_convert_execute_route_consumes_flow(
    case: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prototypes.docx_output.route_plan import execute_routes

    calls = stub(monkeypatch)
    parent, plan = prepare(case)
    child = execute_routes(parent, plan["plan_hash"], plan["request_budget"], True)
    assert calls == ["pp", "monkey"]  # HTTP stub only, not real requests.
    assert read(child / "render-plan.auto.json")["schema_version"] == "render-plan/2"
    assert read(child / "render-manifest.auto.json")["renderer"]["name"] == "flow"
    assert read(child / "qa.json")["pages"][0]["layout_status"] == "ABSTAIN"


def test_api_and_cli_expose_reviewed_page_selection(case: Path) -> None:
    import json
    import subprocess
    import sys

    from fastapi.testclient import TestClient
    from prototypes.docx_output.server import create_app

    job, ir = document(case)
    finish(job, ir)
    finish(job, read(job / "layout.auto.json"), "reviewed")
    with TestClient(
        create_app(output_root=case / "jobs"), base_url="http://127.0.0.1:8765"
    ) as client:
        client.get("/api/session")
        response = client.get("/api/job/" + job.name)
        assert response.status_code == 200
        assert response.json()["qa_reviewed"]["pages"][1]["selected_geometry_provider"] == "pp"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/docx_demo.py",
            "status",
            "--job-id",
            job.name,
            "--output-root",
            str(case / "jobs"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert (
        report["revision"] == "reviewed"
        and report["pages"][0]["selected_geometry_provider"] == "monkey"
    )


def test_shared_worker_failure_keeps_last_structure(
    case: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from prototypes.docx_output.structure_processors import docvortex

    def unavailable(request: Json) -> Json:
        raise DemoError("DOCVORTEX_RUNTIME_UNAVAILABLE")

    job, ir = document(case)
    before = copy.deepcopy(ir["relations"])
    monkeypatch.setattr(docvortex, "call_worker", unavailable)
    qa = finish(job, ir)
    result = read(job / "layout.auto.json")
    assert result["relations"] == before
    assert result["metadata"]["reconstruction"]["structure_status"] == "FALLBACK"
    assert all("SHARED_STRUCTURE_UNAVAILABLE" in p["issue_codes"] for p in qa["pages"][:1])
