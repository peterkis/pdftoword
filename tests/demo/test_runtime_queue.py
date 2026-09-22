"""Persistence, idempotency and recovery use the real local runtime ledger."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from prototypes.docx_output.common import PRIVATE, DemoError, read, save
from prototypes.docx_output.runtime_queue import RuntimeQueue
from tests.demo.synthetic import make_pdf


@pytest.fixture
def root() -> Iterator[Path]:
    p = PRIVATE / ("runtime-test-" + uuid.uuid4().hex)
    yield p
    shutil.rmtree(p, ignore_errors=True)


def test_same_request_is_idempotent_and_restart_preserves_queue(root: Path, tmp_path: Path) -> None:
    source = tmp_path / "input.pdf"
    make_pdf(source)
    with RuntimeQueue(root, autostart=False) as queue:
        a = queue.submit_native(source, "1")
        b = queue.submit_native(source, "1")
        assert a["operation_id"] == b["operation_id"]
    with RuntimeQueue(root, autostart=False) as queue:
        assert len(queue.records()) == 1 and queue.records()[0]["status"] == "QUEUED"


def test_interrupted_work_never_blindly_resubmits(root: Path, tmp_path: Path) -> None:
    source = tmp_path / "input.pdf"
    make_pdf(source)
    with RuntimeQueue(root, autostart=False) as queue:
        op = queue.submit_native(source, "1")
    state = read(root / "queue.json")
    state["operations"][0].update(status="RUNNING", remote_id="remote-123")
    save(root / "queue.json", state)
    with RuntimeQueue(root, autostart=False) as queue:
        row = queue.records()[0]
        assert row["status"] == "SUBMISSION_UNKNOWN" and row["remote_id"] == "remote-123"
        assert queue.submit_native(source, "1")["operation_id"] == op["operation_id"]
        with pytest.raises(DemoError, match="REMOTE_RECOVERY_UNSUPPORTED"):
            queue.retry(op["operation_id"])


def test_cancel_pending_and_reject_second_owner(root: Path, tmp_path: Path) -> None:
    source = tmp_path / "input.pdf"
    make_pdf(source)
    with RuntimeQueue(root, autostart=False) as queue:
        op = queue.submit_native(source, "1")
        queue.cancel(op["operation_id"])
        assert queue.records()[0]["status"] == "CANCELLED"
        with pytest.raises(DemoError, match="RUNTIME_ALREADY_RUNNING"):
            RuntimeQueue(root, autostart=False)


def test_limits_and_symlinks(root: Path, tmp_path: Path) -> None:
    source = tmp_path / "four.pdf"
    make_pdf(source, pages=4)
    with RuntimeQueue(root, autostart=False) as queue:
        with pytest.raises(DemoError):
            queue.submit_native(source, "1-4")
        huge = tmp_path / "huge.pdf"
        with huge.open("wb") as stream:
            stream.truncate(25 * 1024 * 1024 + 1)
        with pytest.raises(DemoError):
            queue.submit_native(huge, "1")
        link = tmp_path / "link.pdf"
        link.symlink_to(source)
        with pytest.raises(DemoError):
            queue.submit_native(link, "1")
        assert queue.records() == []


def test_cache_binds_pages_bytes_and_preserves_retry_source(root: Path, tmp_path: Path) -> None:
    source = tmp_path / "two.pdf"
    make_pdf(source, pages=2)
    with RuntimeQueue(root, autostart=False) as queue:
        first = queue.submit_native(source, "1")
        second = queue.submit_native(source, "2")
        copy = tmp_path / "renamed.pdf"
        shutil.copyfile(source, copy)
        assert queue.submit_native(copy, "1")["operation_id"] == first["operation_id"]
        assert first["cache_key"] != second["cache_key"]
        queue.cancel(first["operation_id"])
        retry = queue.retry(first["operation_id"])
        assert retry["operation_id"] != first["operation_id"]
        assert retry["details"]["source"] == first["details"]["source"]
        assert queue.records()[0]["status"] == "CANCELLED"
        assert (root / retry["details"]["source"]).read_bytes() == source.read_bytes()


def test_disk_full_does_not_publish_job(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import errno

    from prototypes.docx_output import runtime_queue

    source = tmp_path / "source.pdf"
    make_pdf(source)
    with RuntimeQueue(root, autostart=False) as queue:
        before = (root / "queue.json").read_bytes()

        def fail(*args: object, **kwargs: object) -> None:
            raise OSError(errno.ENOSPC, "simulated")

        monkeypatch.setattr(runtime_queue.shutil, "copyfile", fail)
        with pytest.raises(OSError) as caught:
            queue.submit_native(source, "1")
        assert runtime_queue.error_code(caught.value) == "DISK_FULL"
        assert queue.records() == []
        assert (root / "queue.json").read_bytes() == before
        assert not list(root.rglob("*.pending"))


def test_execution_lock_serializes_review_and_queue(root: Path, tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    make_pdf(source)
    with RuntimeQueue(root, autostart=False) as queue:
        queue.submit_native(source, "1")
        with queue.exclusive_output():
            assert queue.run_next() is False
            with pytest.raises(DemoError, match="JOB_BUSY"), queue.exclusive_output():
                pass
        assert queue.records()[0]["status"] == "QUEUED"


def test_real_worker_receipt_offline_export_and_damage(root: Path, tmp_path: Path) -> None:
    from prototypes.docx_output.common import digest

    source = tmp_path / "source.pdf"
    make_pdf(source)
    with RuntimeQueue(root, autostart=False) as queue:
        native = queue.submit_native(source, "1")
        assert queue.run_next()
        row = queue.records()[0]
        assert row["status"] in {"SUCCEEDED", "PARTIAL"}, row
        job = root / row["job_id"]
        original = digest(job / "auto.docx")
        exported = queue.submit_export(job)
        assert exported["cache_key"] != native["cache_key"]
        assert queue.run_next()
        result = queue.records()[-1]
        assert result["status"] in {"SUCCEEDED", "PARTIAL"}, result
        assert digest(job / "auto.docx") == original
        assert (
            read(root / "requests" / result["operation_id"] / "receipt.json")["model_call_count"]
            == 0
        )
        (job / "auto.docx").write_bytes(b"damaged")
        with pytest.raises(DemoError, match="OUTPUT_ASSET_DAMAGED"):
            queue.submit_native(source, "1")


def test_interrupted_receipt_is_adopted_without_reprocessing(root: Path, tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    make_pdf(source)
    with RuntimeQueue(root, autostart=False) as queue:
        queue.submit_native(source, "1")
        queue.run_next()
        state = read(root / "queue.json")
        job_id = state["operations"][0]["job_id"]
    state["operations"][0]["status"] = "RUNNING"
    save(root / "queue.json", state)
    with RuntimeQueue(root, autostart=False) as queue:
        assert queue.records()[0]["status"] in {"SUCCEEDED", "PARTIAL"}
        assert queue.records()[0]["job_id"] == job_id
        assert not queue.run_next()


def test_failed_atomic_docx_replace_preserves_previous(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import errno

    from prototypes.docx_output import writer
    from prototypes.docx_output.pipeline import convert

    source = tmp_path / "source.pdf"
    make_pdf(source)
    job = convert(source, "1", "native", root)
    ir = read(job / "layout.auto.json")
    writer.build(job, ir, "reviewed")
    old = (job / "reviewed.docx").read_bytes()

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError(errno.ENOSPC, "simulated")

    monkeypatch.setattr(writer.os, "replace", fail)
    with pytest.raises(OSError):
        writer.build(job, ir, "reviewed")
    assert (job / "reviewed.docx").read_bytes() == old
    assert not list(job.glob("*.pending"))


def test_runtime_api_review_download_restart_and_live_block(root: Path, tmp_path: Path) -> None:
    import time

    from fastapi.testclient import TestClient
    from prototypes.docx_output.common import digest
    from prototypes.docx_output.server import create_app

    source = tmp_path / "source.pdf"
    make_pdf(source)
    with TestClient(
        create_app(output_root=root, runtime=True), base_url="http://127.0.0.1:8765"
    ) as client:
        session = client.get("/api/session").json()
        assert session["runtime"]
        headers = {"origin": "http://127.0.0.1:8765", "x-demo-session": session["token"]}
        assert client.post("/api/route/run", headers=headers).status_code == 403
        response = client.post(
            "/api/upload",
            headers=headers,
            data={"mode": "native", "pages": "1", "output_profile": "fidelity-v3.1"},
            files={"file": ("source.pdf", source.read_bytes(), "application/pdf")},
        )
        assert response.status_code == 200, response.text
        for _ in range(200):
            state = client.get("/api/status").json()
            if not state["busy"]:
                break
            time.sleep(0.02)
        assert state["state"] in {"待复核", "部分完成"}, state
        job = root / state["job_id"]
        before = digest(job / "auto.docx")
        ir = read(job / "layout.auto.json")
        block = next(b for p in ir["pages"] for b in p["blocks"] if b["type"] == "paragraph")
        operations = {
            "operations": [
                {
                    "block_id": block["id"],
                    "action": "text",
                    "text": "F4 diagnostic edit",
                    "reason": "runtime test",
                }
            ]
        }
        marker = job / "~$viewed.docx"
        marker.write_text("lock")
        locked = client.post("/api/review/" + job.name, headers=headers, json=operations)
        assert locked.status_code == 400 and "WORD_DOCUMENT_OPEN" in locked.text
        marker.unlink()
        result = client.post("/api/review/" + job.name, headers=headers, json=operations)
        assert result.status_code == 200, result.text
        assert digest(job / "auto.docx") == before
        reviewed = (job / "reviewed.docx").read_bytes()
    with TestClient(
        create_app(output_root=root, runtime=True), base_url="http://127.0.0.1:8765"
    ) as client:
        client.get("/api/session")
        assert (job / "reviewed.docx").read_bytes() == reviewed
        assert client.get("/api/status").json()["job_id"] == job.name


def test_cancel_active_child_and_preserve_input(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess
    import sys
    import threading
    import time
    from typing import Any

    from prototypes.docx_output import runtime_queue

    original = subprocess.Popen
    started = threading.Event()

    def slow(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        child = original([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
        started.set()
        return child

    source = tmp_path / "source.pdf"
    make_pdf(source)
    monkeypatch.setattr(runtime_queue.subprocess, "Popen", slow)
    with RuntimeQueue(root) as queue:
        row = queue.submit_native(source, "1")
        assert started.wait(5)
        queue.cancel(row["operation_id"])
        for _ in range(300):
            if queue.records()[0]["status"] == "CANCELLED":
                break
            time.sleep(0.02)
        assert not queue.last_error, queue.last_error
        assert queue.records()[0]["status"] == "CANCELLED"
        assert (root / row["details"]["source"]).read_bytes() == source.read_bytes()


def test_malformed_ledger_is_not_overwritten(root: Path) -> None:
    from prototypes.docx_output.common import private_dir

    private_dir(root)
    save(root / "queue.json", {"schema_version": "bad", "operations": []})
    before = (root / "queue.json").read_bytes()
    with pytest.raises(DemoError, match="QUEUE_LEDGER_DAMAGED"):
        RuntimeQueue(root, autostart=False)
    assert (root / "queue.json").read_bytes() == before
