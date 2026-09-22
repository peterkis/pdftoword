"""One durable local operation ledger and one OS-locked worker; no remote submission."""

from __future__ import annotations

import copy
import errno
import fcntl
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

from .common import (
    PRIVATE,
    ROOT,
    DemoError,
    Json,
    digest,
    private_dir,
    read,
    safe_path,
    save,
    validate,
    validate_input,
)
from .input_analysis import PDFIUM_LOCK, open_pdf
from .native_pdf import parse_pages
from .render_replay import inventory, verify_source

PAGE_LIMIT = 3
ACTIVE = {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}
FINISHED = {"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED", "INTERRUPTED", "SUBMISSION_UNKNOWN"}


def error_code(exc: BaseException) -> str:
    """Return a bounded actionable code without source text or local private paths."""
    if isinstance(exc, DemoError):
        return str(exc)
    if isinstance(exc, OSError):
        return {
            errno.ENOSPC: "DISK_FULL",
            errno.EACCES: "DIRECTORY_PERMISSION_DENIED",
            errno.EPERM: "FILE_LOCKED_OR_PERMISSION_DENIED",
        }.get(exc.errno or 0, "LOCAL_IO_FAILED")
    return type(exc).__name__


def identity(value: Json) -> str:
    """Hash complete request semantics, never a filename-only cache key."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def implementation_identity() -> Json:
    """Bind cache entries to renderer, parser versions, configuration and schemas."""
    paths = [
        *Path(__file__).parent.rglob("*.py"),
        *(ROOT / "specs").glob("*.json"),
        ROOT / "config/profiles/fidelity-v3.1.json",
        ROOT / "config/font-mapping.yaml",
    ]
    return {
        "files": {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)},
        "versions": {n: version(n) for n in ["pypdfium2", "pdf-inspector", "python-docx", "lxml"]},
    }


class RuntimeQueue:
    """queue.json is authoritative; output state.json remains a pipeline diagnostic only."""

    def __init__(self, root: Path, *, autostart: bool = True) -> None:
        self.root = root.absolute()
        private_dir(self.root)
        self._mutex = threading.RLock()
        self._stop = threading.Event()
        self._process: subprocess.Popen[bytes] | None = None
        self._active_id: str | None = None
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None
        path = safe_path(self.root, ".owner.lock")
        self._owner = path.open("a+b")
        path.chmod(0o600)
        try:
            fcntl.flock(self._owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._owner.close()
            raise DemoError("RUNTIME_ALREADY_RUNNING") from None
        self._identity = implementation_identity()
        try:
            self.data: Json = (
                read(safe_path(self.root, "queue.json"))
                if (self.root / "queue.json").exists()
                else {"schema_version": "local-queue/1", "operations": []}
            )
            if (
                self.data.get("schema_version") != "local-queue/1"
                or not isinstance(self.data.get("operations"), list)
                or any(
                    not isinstance(r, dict)
                    or not {"operation_id", "status", "kind", "cache_key", "details"} <= r.keys()
                    for r in self.data["operations"]
                )
            ):
                raise DemoError("QUEUE_LEDGER_DAMAGED")
            for row in self.data["operations"]:
                if row["status"] in {
                    "RUNNING",
                    "CANCEL_REQUESTED",
                    "SUBMITTING",
                    "SUBMITTED",
                    "DOWNLOADING",
                }:
                    row["status"] = (
                        "SUBMISSION_UNKNOWN"
                        if row.get("remote_id") or row.get("kind") == "remote"
                        else "INTERRUPTED"
                    )
                    row["message"] = (
                        "上次执行被中断；不会自动重发。远端任务可能仍运行。"
                        if row["status"] == "SUBMISSION_UNKNOWN"
                        else "上次本地执行被中断；保留文件，显式重试后另建输出。"
                    )
            self._write()
            self._receipts()
        except BaseException:
            self._owner.close()
            raise
        if autostart:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def __enter__(self) -> RuntimeQueue:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _write(self) -> None:
        save(self.root / "queue.json", self.data)

    def records(self) -> list[Json]:
        with self._mutex:
            return copy.deepcopy(self.data["operations"])

    def _row(self, operation_id: str) -> Json:
        found = next(
            (r for r in self.data["operations"] if r["operation_id"] == operation_id), None
        )
        if found is None:
            raise DemoError("OPERATION_NOT_FOUND")
        return cast(Json, found)

    def _deduplicate(self, key: str) -> Json | None:
        for row in reversed(self.data["operations"]):
            if row["cache_key"] == key:
                # Reuse completed results only after checking the committed manifest.
                if row["status"] in {"SUCCEEDED", "PARTIAL"}:
                    self._verify_receipt(row)
                return {**copy.deepcopy(row), "reused": True}
        return None

    def _allocate(self, kind: str, key: str, details: Json) -> Json:
        if sum(r["status"] in ACTIVE for r in self.data["operations"]) >= 8:
            raise DemoError("QUEUE_CAPACITY_REACHED")
        op = "op-" + uuid.uuid4().hex
        directory = self.root / "requests" / op
        private_dir(directory)
        return {
            "operation_id": op,
            "kind": kind,
            "cache_key": key,
            "status": "QUEUED",
            "created_at": time.time(),
            "details": details,
            "model_call_count": 0,
            "message": "等待本地串行执行",
        }

    def _publish(self, row: Json) -> Json:
        save(self.root / "requests" / row["operation_id"] / "request.json", row)
        self.data["operations"].append(row)
        try:
            self._write()
        except BaseException:
            self.data["operations"].pop()
            raise
        return copy.deepcopy(row)

    def submit_native(self, source: Path, pages: str | None) -> Json:
        validate_input(source)
        if source.suffix.lower() != ".pdf":
            raise DemoError("NATIVE_REQUIRES_PDF")
        with PDFIUM_LOCK:
            doc = open_pdf(source)
            try:
                selected = parse_pages(pages, len(doc), page_limit=PAGE_LIMIT)
            finally:
                doc.close()
        parse_key = {
            "input_sha256": digest(source),
            "pages": [i + 1 for i in selected],
            "preprocessing": "native_effective_cropbox_pdfium_scale2_max4000",
            "provider": "native",
            "revision": self._identity,
            "schema": "layout-ir/1.2",
        }
        details = {
            "pages": ",".join(str(i + 1) for i in selected),
            "parse_identity": identity(parse_key),
            "input_sha256": parse_key["input_sha256"],
            "requested_pages": parse_key["pages"],
            "profile": "fidelity-v3.1",
            "render_identity": identity(
                {"profile": "fidelity-v3.1", "implementation": self._identity}
            ),
        }
        key = identity(details)
        with self._mutex:
            if (prior := self._deduplicate(key)) is not None:
                return prior
            row = self._allocate("native", key, details)
            target = self.root / "requests" / row["operation_id"] / "input.pdf"
            pending = target.with_suffix(".pending")
            try:
                shutil.copyfile(source, pending)
                pending.chmod(0o600)
                if digest(pending) != details["input_sha256"]:
                    raise DemoError("INPUT_CHANGED_DURING_UPLOAD")
                os.replace(pending, target)
            finally:
                pending.unlink(missing_ok=True)
            row["details"]["source"] = str(target.relative_to(self.root))
            return self._publish(row)

    def submit_export(
        self, source: Path, revision: str = "auto", style: Json | None = None
    ) -> Json:
        if revision not in {"auto", "reviewed"}:
            raise DemoError("INVALID_REVISION")
        source = source.absolute()
        if source.is_symlink():
            raise DemoError("SYMLINK_REJECTED")
        hashes = inventory(source)
        ir = read(safe_path(source, f"layout.{revision}.json"))
        validate(ir)
        verify_source(source, ir, hashes)
        if sum(safe_path(source, p).stat().st_size for p in hashes) > 256 * 1024 * 1024:
            raise DemoError("SAVED_JOB_IMPORT_LIMIT")
        details = {
            "revision": revision,
            "source_files": hashes,
            "layout_sha256": hashes[f"layout.{revision}.json"],
            "style": style or {},
            "profile": "fidelity-v3.1",
            "render_identity": identity(self._identity),
            "requested_pages": [p["page_index"] + 1 for p in ir["pages"]],
        }
        key = identity(details)
        with self._mutex:
            if (prior := self._deduplicate(key)) is not None:
                return prior
            row = self._allocate("export", key, details)
            target = self.root / "requests" / row["operation_id"] / "source"
            private_dir(target)
            for name, sha in hashes.items():
                dest = safe_path(target, name)
                private_dir(dest.parent)
                shutil.copyfile(safe_path(source, name), dest)
                dest.chmod(0o600)
                if digest(dest) != sha:
                    raise DemoError("SOURCE_CHANGED_DURING_IMPORT")
            if inventory(source) != hashes:
                raise DemoError("SOURCE_CHANGED_DURING_IMPORT")
            row["details"]["source"] = str(target.relative_to(self.root))
            return self._publish(row)

    def cancel(self, operation_id: str) -> Json:
        with self._mutex:
            row = self._row(operation_id)
            if row["status"] == "QUEUED":
                row["status"] = "CANCELLED"
            elif row["status"] == "RUNNING":
                row["status"] = "CANCEL_REQUESTED"
            row["message"] = (
                "停止本地等待；不会声称已取消远端任务。"
                if row.get("remote_id")
                else "已请求停止本地工作；保留输入、自动结果及人工稿。"
            )
            self._write()
            return copy.deepcopy(row)

    def retry(self, operation_id: str) -> Json:
        with self._mutex:
            original = self._row(operation_id)
            if original.get("remote_id") or original["status"] == "SUBMISSION_UNKNOWN":
                raise DemoError("REMOTE_RECOVERY_UNSUPPORTED")
            if original["status"] not in {"INTERRUPTED", "FAILED", "CANCELLED"}:
                raise DemoError("RETRY_NOT_ALLOWED")
            row = self._allocate(
                original["kind"], original["cache_key"], copy.deepcopy(original["details"])
            )
            row["retry_of"] = operation_id
            return self._publish(row)

    @contextmanager
    def exclusive_output(self) -> Iterator[None]:
        """UI review and pipeline jobs share the same single execution lock."""
        path = safe_path(self.root, ".execution.lock")
        with path.open("a+b") as handle:
            path.chmod(0o600)
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DemoError("JOB_BUSY") from None
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _verify_receipt(self, row: Json) -> Json:
        receipt = read(safe_path(self.root, f"requests/{row['operation_id']}/receipt.json"))
        job = safe_path(self.root, receipt["job_id"])
        for name, sha in receipt["files"].items():
            asset = safe_path(job, name)
            if not asset.is_file() or digest(asset) != sha:
                raise DemoError("OUTPUT_ASSET_DAMAGED")
        return receipt

    def _receipts(self) -> None:
        changed = False
        for row in self.data["operations"]:
            if row["status"] not in {"RUNNING", "INTERRUPTED"}:
                continue
            if (self.root / "requests" / row["operation_id"] / "receipt.json").exists():
                receipt = self._verify_receipt(row)
                changed = True
                row.update(
                    status=receipt["status"],
                    job_id=receipt["job_id"],
                    message="本地输出已保存；请检查待复核项。",
                    missing_pages=receipt["missing_pages"],
                )
        if changed:
            self._write()

    def _loop(self) -> None:
        while not self._stop.wait(0.15):
            try:
                self.run_next()
            except Exception as exc:
                self.last_error = error_code(exc)

    def run_next(self) -> bool:
        with self._mutex:
            self._receipts()
            row = next((r for r in self.data["operations"] if r["status"] == "QUEUED"), None)
            if row is None:
                return False
            handle = safe_path(self.root, ".execution.lock").open("a+b")
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                return False
            self.last_error = None
            row["status"] = "RUNNING"
            row["message"] = "本地处理，模型调用0"
            self._active_id = row["operation_id"]
            try:
                self._write()
            except BaseException:
                row["status"] = "QUEUED"
                self._active_id = None
                handle.close()
                raise
            env = dict(os.environ)
            env["P2W_PRIVATE_ROOT"] = str(PRIVATE)
            env["P2W_RUNTIME_ROOT"] = str(self.root)
            payload = self.root / "requests" / row["operation_id"] / "request.json"
            log = payload.with_name("worker.log")
            try:
                stream = log.open("wb")
                log.chmod(0o600)
            except BaseException:
                handle.close()
                row["status"] = "INTERRUPTED"
                self._active_id = None
                raise
            # The inherited lock survives an owner crash until this child exits.
            try:
                self._process = subprocess.Popen(
                    [sys.executable, "-I", str(ROOT / "scripts/runtime_worker.py"), str(payload)],
                    env=env,
                    stdout=stream,
                    stderr=stream,
                    start_new_session=True,
                    pass_fds=(handle.fileno(),),
                )
            except BaseException:
                handle.close()
                stream.close()
                row["status"] = "FAILED"
                row["code"] = "WORKER_START_FAILED"
                self._write()
                raise
            process = self._process
        try:
            while process.poll() is None:
                if self._stop.wait(0.1) or row["status"] == "CANCEL_REQUESTED":
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            with self._mutex:
                if row["status"] == "CANCEL_REQUESTED":
                    row["status"] = "CANCELLED"
                elif self._stop.is_set():
                    row["status"] = "INTERRUPTED"
                elif process.returncode == 0 and payload.with_name("receipt.json").exists():
                    self._receipts()
                else:
                    row["status"] = "FAILED"
                    failure = payload.with_name("failure.json")
                    row["code"] = (
                        read(failure).get("code", "WORKER_FAILED")
                        if failure.exists()
                        else "WORKER_INTERRUPTED_OR_DISK_FULL"
                    )
                self._write()
        finally:
            stream.close()
            handle.close()
            self._process = None
            self._active_id = None
        return True

    def status(self) -> Json:
        rows = self.records()
        active = next((r for r in rows if r["status"] in ACTIVE), None)
        row = active or (rows[-1] if rows else {})
        labels = {
            "QUEUED": "等待",
            "RUNNING": "运行",
            "CANCEL_REQUESTED": "正在取消",
            "SUCCEEDED": "待复核",
            "PARTIAL": "部分完成",
            "FAILED": "失败",
            "CANCELLED": "已取消",
            "INTERRUPTED": "中断，未自动重试",
            "SUBMISSION_UNKNOWN": "提交状态未知，未重发",
        }
        return {
            "state": labels.get(row.get("status", ""), "准备"),
            "busy": active is not None,
            "job_id": row.get("job_id"),
            "operation_id": row.get("operation_id"),
            "code": self.last_error or row.get("code"),
            "operations": rows,
            "runtime": True,
            "capacity": {"pages": PAGE_LIMIT, "bytes": 25 * 1024 * 1024, "concurrency": 1},
            "live_models": False,
        }

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._owner.close()
