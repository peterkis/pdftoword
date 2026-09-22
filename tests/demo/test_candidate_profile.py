"""User-entry candidate exports preserve defaults, lineage and offline review."""

from __future__ import annotations

import socket
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from fastapi.testclient import TestClient
from prototypes.docx_output.common import DemoError, block, digest, read
from prototypes.docx_output.pipeline import convert, export, finish
from prototypes.docx_output.render_replay import inventory
from prototypes.docx_output.server import create_app
from prototypes.docx_output.style_replay import export_style
from tests.demo.synthetic import make_pdf
from tests.demo.test_option_row_layout import option_case

from docx_demo import main


def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail every socket connection during conversion/review."""

    def denied(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("NETWORK_FORBIDDEN")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def frozen_job(root: Path) -> Path:
    """A previously generated scan IR, never sent through structure processing again."""
    job, ir = option_case(root)
    note = block("note", 0, [10, 200, 300, 230], "Review this text.", "inferred")
    ir["pages"][0]["blocks"].append(note)
    ir["pages"][0]["reading_order"].append("note")
    finish(job, ir)
    return job


def wait_job(client: TestClient) -> str:
    """Poll only the local in-process worker with a bounded deadline."""
    for _ in range(500):
        state = client.get("/api/status").json()
        if not state.get("busy"):
            assert state["state"] != "失败", state
            return str(state["job_id"])
        time.sleep(0.01)
    raise AssertionError("WORKER_TIMEOUT")


def test_native_cli_candidate_and_legacy_default(
    private_case: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = private_case / "native.pdf"
    make_pdf(source)
    block_network(monkeypatch)
    base = convert(source, "1", output_root=private_case / "legacy")
    assert read(base / "qa.json")["output_profile"]["id"] == "legacy"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docx_demo",
            "convert",
            "--input",
            str(source),
            "--mode",
            "native",
            "--pages",
            "1",
            "--output-profile",
            "fidelity-v3.1",
            "--output-root",
            str(private_case / "candidate"),
        ],
    )
    assert main() == 0
    job = Path(capsys.readouterr().out.strip()).parent
    assert read(job / "layout.auto.json")["schema_version"] == "layout-ir/1.2"
    assert read(job / "qa.json")["output_profile"]["id"] == "fidelity-v3.1"
    assert read(job / "render-manifest.auto.json")["renderer"]["name"] == "flow"
    assert read(job / "request-manifest.json")["model_call_count"] == 0
    assert read(job / "layout.auto.json")["pages"] == read(base / "layout.auto.json")["pages"]


def test_api_frozen_candidate_review_and_reviewed_replay(
    private_case: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = frozen_job(private_case)
    before = inventory(source)
    block_network(monkeypatch)
    from prototypes.docx_output.structure_processors.docvortex import DocVortexStructureProcessor

    def forbidden_structure(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("REPEATED_STRUCTURE_PROCESSING")

    monkeypatch.setattr(DocVortexStructureProcessor, "process", forbidden_structure)
    with TestClient(
        create_app(output_root=source.parent), base_url="http://127.0.0.1:8765"
    ) as client:
        token = client.get("/api/session").json()["token"]
        headers = {"origin": "http://127.0.0.1:8765", "x-demo-session": token}
        assert client.post("/api/replay-job/" + source.name, json={}).status_code == 403
        response = client.post(
            "/api/replay-job/" + source.name,
            json={"output_profile": "fidelity-v3.1"},
            headers=headers,
        )
        assert response.status_code == 200
        job = source.parent / wait_job(client)
        data = client.get("/api/job/" + job.name).json()
        assert data["qa"]["output_profile"]["id"] == "fidelity-v3.1"
        assert data["auto"]["document_id"] == job.name
        assert data["auto"]["metadata"]["parent_output"]["job_id"] == source.name
        assert len(Document(str(job / "auto.docx")).tables[0].columns) == 4
        auto_hash = digest(job / "auto.docx")
        operations = {
            "operations": [
                {
                    "block_id": "note",
                    "action": "text",
                    "text": "Local edit.",
                    "reason": "Controlled review test",
                }
            ]
        }
        assert (
            client.post("/api/review/" + job.name, json=operations, headers=headers).status_code
            == 200
        )
        reviewed = read(job / "layout.reviewed.json")
        assert (
            next(b for p in reviewed["pages"] for b in p["blocks"] if b["id"] == "note")["content"][
                "plain_text"
            ]
            == "Local edit."
        )
        assert read(job / "qa.reviewed.json")["output_profile"]["id"] == "fidelity-v3.1"
        assert digest(job / "auto.docx") == auto_hash
        export(job)
        assert digest(job / "auto.docx") == auto_hash
        response = client.post(
            "/api/replay-job/" + job.name,
            json={"output_profile": "fidelity-v3.1", "revision": "reviewed"},
            headers=headers,
        )
        assert response.status_code == 200
        child = source.parent / wait_job(client)
        assert read(child / "layout.auto.json")["pages"] == reviewed["pages"]
        assert (
            read(child / "layout.auto.json")["metadata"]["parent_output"]["revision"] == "reviewed"
        )
    assert inventory(source) == before


def test_upload_candidate_uses_same_profile(
    private_case: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = private_case / "native.pdf"
    make_pdf(source)
    block_network(monkeypatch)
    with TestClient(
        create_app(output_root=private_case / "jobs"), base_url="http://127.0.0.1:8765"
    ) as client:
        token = client.get("/api/session").json()["token"]
        response = client.post(
            "/api/upload",
            files={"file": ("native.pdf", source.read_bytes(), "application/pdf")},
            data={"mode": "native", "pages": "1", "output_profile": "fidelity-v3.1"},
            headers={"origin": "http://127.0.0.1:8765", "x-demo-session": token},
        )
        assert response.status_code == 200
        job = private_case / "jobs" / wait_job(client)
        assert read(job / "qa.json")["output_profile"]["id"] == "fidelity-v3.1"
        assert read(job / "request-manifest.json")["model_call_count"] == 0


def test_frozen_rejects_nested_output_and_asset_drift(private_case: Path) -> None:
    source = frozen_job(private_case)
    sha = digest(source / "layout.auto.json")
    with pytest.raises(DemoError, match="OUTPUT_INSIDE_SOURCE"):
        export_style(source, source / "nested", {}, sha, output_profile="fidelity-v3.1")
    ir = read(source / "layout.auto.json")
    (source / ir["assets"][0]["path"]).write_bytes(b"changed")
    with pytest.raises(DemoError, match="ASSET_SEAL"):
        export_style(source, private_case / "bad", {}, sha, output_profile="fidelity-v3.1")
    assert not (private_case / "bad").exists()


def test_unknown_profile_does_not_create_job(private_case: Path) -> None:
    source = private_case / "native.pdf"
    make_pdf(source)
    with pytest.raises(DemoError, match="UNKNOWN_OUTPUT_PROFILE"):
        convert(source, "1", output_root=private_case / "bad", output_profile="unknown")
    assert not (private_case / "bad").exists()
