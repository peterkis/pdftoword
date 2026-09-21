"""Single-admission execution; online resume never uploads or submits again."""

from __future__ import annotations

import json
import os
import shutil
import time
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .common import (
    ARMS,
    ExperimentError,
    Json,
    digest,
    frozen,
    inspect_docx,
    load_local_environment,
    now,
    quiet_upstream,
    read,
    safe_path,
    seal,
    write,
)

API = "https://mineru.net/api/v4"
TERMINAL = {"COMPLETE", "PARTIAL", "FAILED", "BLOCKED", "DOWNLOAD_FAILED"}


def request_body(group: str, data: Json, arm: str, data_id: str) -> Json:
    """The OCR flag belongs to each file, never only the batch root."""
    return {
        "files": [
            {
                "name": f"{group}.pdf",
                "data_id": data_id,
                "is_ocr": True,
                "page_ranges": f"1-{len(data['pages'])}",
            }
        ],
        "model_version": ARMS[arm],
        "language": data["language"],
        "enable_formula": True,
        "enable_table": True,
        "extra_formats": ["docx"],
    }


def remote_url(value: str) -> str:
    """Accept only HTTPS destinations within the official service's storage origins."""
    parsed = urlsplit(value)
    hosts = {
        "mineru.oss-cn-shanghai.aliyuncs.com",
        "cdn-mineru.openxlab.org.cn",
        "oss-mineru.openxlab.org.cn",
        "mineru.oss-cn-hangzhou.aliyuncs.com",
    }
    if (
        parsed.scheme != "https"
        or parsed.hostname not in hosts
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ExperimentError("UNAPPROVED_RESULT_OR_UPLOAD_ORIGIN")
    return value


def extract_zip(source: Path, target: Path) -> None:
    """Confined extraction, bounded expansion, no links or duplicate member names."""
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        if len(infos) > 10000 or sum(i.file_size for i in infos) > 1024**3:
            raise ExperimentError("RESULT_ZIP_LIMIT")
        if len({i.filename for i in infos}) != len(infos):
            raise ExperimentError("RESULT_ZIP_DUPLICATE")
        for info in infos:
            name = info.filename.rstrip("/")
            safe_path(target, name)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ExperimentError("RESULT_ZIP_SYMLINK")
        target.mkdir(parents=True, exist_ok=False)
        for info in infos:
            if info.is_dir():
                continue
            path = safe_path(target, info.filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as output, archive.open(info) as stream:
                shutil.copyfileobj(stream, output)


def record_http(folder: Path, method: str, purpose: str, status: int | None) -> None:
    """Append method/status only, excluding headers, URLs, source text and credentials."""
    with (folder / "http.jsonl").open("a") as stream:
        stream.write(
            json.dumps({"at": now(), "method": method, "purpose": purpose, "status_code": status})
            + "\n"
        )


def api_call(
    client: httpx.Client,
    folder: Path,
    method: str,
    route: str,
    token: str,
    body: Json | None = None,
) -> Json:
    """Send a single API request, immediately persisting the private raw response."""
    status = None
    try:
        response = client.request(
            method, API + route, headers={"Authorization": "Bearer " + token}, json=body
        )
        status = response.status_code
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ExperimentError("API_RESPONSE_SCHEMA")
        history = folder / "responses"
        history.mkdir(exist_ok=True)
        write(history / f"{len(list(history.iterdir())):05d}.json", result)
        if result.get("code") != 0:
            raise ExperimentError("API_REPORTED_ERROR")
        return result
    finally:
        record_http(folder, method, "official_api", status)


def collect(folder: Path, token: str, timeout: int = 1800, interval: int = 10) -> Json:
    """Poll a persisted ID and download its result; no upload code in this function."""
    receipt = read(folder / "receipt.json")
    remote = read(folder / "remote-state.json")
    deadline = time.monotonic() + timeout
    with httpx.Client(
        timeout=httpx.Timeout(120, connect=10), follow_redirects=False, trust_env=False
    ) as client:
        url = remote.get("full_zip_url")
        while not url:
            result = api_call(
                client, folder, "GET", "/extract-results/batch/" + remote["batch_id"], token
            )
            rows = result.get("data", {}).get("extract_result", [])
            matching = [r for r in rows if r.get("data_id") == receipt["data_id"]]
            if not matching:
                matching = [r for r in rows if r.get("file_name") == receipt["group"] + ".pdf"]
            if len(matching) > 1:
                raise ExperimentError("AMBIGUOUS_REMOTE_RESULT")
            state = matching[0].get("state") if matching else "pending"
            receipt["remote_status"] = state
            receipt["updated_at"] = now()
            write(folder / "receipt.json", receipt)
            if state == "failed":
                receipt.update(status="FAILED", error="REMOTE_PARSE_FAILED")
                write(folder / "receipt.json", receipt)
                return receipt
            if state == "done":
                url = remote_url(matching[0]["full_zip_url"])
                remote["full_zip_url"] = url
                write(folder / "remote-state.json", remote)
                break
            if time.monotonic() >= deadline:
                receipt.update(status="PENDING_REMOTE", error="POLL_DEADLINE")
                write(folder / "receipt.json", receipt)
                return receipt
            time.sleep(interval)
        artifacts = folder / "artifacts"
        artifacts.mkdir(exist_ok=True)
        zip_path = artifacts / "result.zip"
        if not zip_path.exists():
            status = None
            try:
                # This client has no Authorization default: credentials cannot cross origins.
                with client.stream("GET", remote_url(url)) as response:
                    status = response.status_code
                    response.raise_for_status()
                    size = 0
                    with zip_path.with_suffix(".zip.part").open("wb") as stream:
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > 512 * 1024**2:
                                raise ExperimentError("DOWNLOAD_SIZE_LIMIT")
                            stream.write(chunk)
                zip_path.with_suffix(".zip.part").replace(zip_path)
            finally:
                record_http(folder, "GET", "official_result_storage", status)
        result_dir = artifacts / "result"
        if not result_dir.exists():
            extract_zip(zip_path, result_dir)
        candidates = list(result_dir.rglob("full.docx"))
        if len(candidates) != 1:
            raise ExperimentError("OFFICIAL_DOCX_MISSING_OR_AMBIGUOUS")
        docx = candidates[0]
        receipt["docx_inventory"] = inspect_docx(docx.read_bytes())
        shutil.copyfile(docx, artifacts / "B.docx")
        layouts = list(result_dir.rglob("layout.json"))
        if len(layouts) == 1:
            layout = read(layouts[0])
            receipt["actual_backend"] = {
                k: layout.get(k, "unknown")
                for k in ("_backend", "_version_name", "_effort", "_ocr_enable")
            }
        receipt.update(status="COMPLETE", docx_sha256=digest(docx), updated_at=now())
        seal(artifacts)
        write(folder / "receipt.json", receipt)
        return receipt


def run_project(run: Path, folder: Path, group: Json, receipt: Json) -> Json:
    """Use the frozen A route and preserve every actual fallback and request."""
    from prototypes.docx_output.route_plan import execute_routes

    prepared = group["A"]
    if prepared["status"] != "PREPARED":
        raise ExperimentError("PROJECT_PREPARE_FAILED")
    parent = run / prepared["job"]
    child = None
    try:
        with quiet_upstream():
            child = execute_routes(parent, prepared["plan_hash"], prepared["budget"], True)
    except Exception as exc:
        receipt.update(
            status="FAILED", error="PROJECT_EXECUTION_FAILED", error_type=type(exc).__name__
        )
        if (parent / "route-execution.json").exists():
            journal = read(parent / "route-execution.json")
            if journal.get("child_job_id"):
                child = parent.parent / journal["child_job_id"]
    if child:
        receipt["project_job"] = child.relative_to(run).as_posix()
        artifacts = folder / "artifacts"
        artifacts.mkdir()
        shutil.copytree(child, artifacts / "project")
        if (child / "request-manifest.json").exists():
            manifest = read(child / "request-manifest.json")
            receipt["model_calls"] = manifest["model_call_count"]
            receipt["request_budget"] = manifest["budget"]
        if (child / "auto.docx").exists():
            shutil.copyfile(child / "auto.docx", artifacts / "A.docx")
            receipt["docx_inventory"] = inspect_docx((artifacts / "A.docx").read_bytes())
            receipt["docx_sha256"] = digest(artifacts / "A.docx")
            layout = read(child / "layout.auto.json")
            receipt["issues_count"] = len(layout.get("issues", []))
            receipt["status"] = "PARTIAL" if receipt["issues_count"] else "COMPLETE"
        seal(artifacts)
    return receipt


def execute(
    run: Path,
    arm: str,
    group_name: str,
    token_file: Path | None,
    resume: bool = False,
    timeout: int = 1800,
) -> Json:
    """Reserve exactly one run per group/arm; serialize all inference with a lock."""
    run = run.resolve()
    load_local_environment()
    manifest = frozen(run)
    folder = run / "runs" / group_name / arm
    lock = run / "active.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ExperimentError("ANOTHER_EXECUTION_OR_UNCLEAN_EXIT") from exc
    os.close(fd)
    try:
        if not resume:
            for p in (run / "runs").glob("*/*/receipt.json"):
                old = read(p)
                if old["status"] not in TERMINAL:
                    raise ExperimentError("PRIOR_TASK_NEEDS_RESUME_OR_RESOLUTION")
            folder.mkdir(parents=True, exist_ok=False, mode=0o700)
            receipt: Json = {
                "arm": arm,
                "group": group_name,
                "status": "STARTED",
                "at": now(),
                "data_id": run.name + "-" + group_name + "-" + arm,
                "parse_submissions": 0,
                "retries": 0,
                "model_calls": 0,
                "word_open": "NOT_RUN",
                "human_acceptance": "PENDING",
            }
            write(folder / "receipt.json", receipt)
        else:
            if arm == "A":
                raise ExperimentError("PROJECT_RETRY_NOT_SUPPORTED")
            receipt = read(folder / "receipt.json")
            if receipt["status"] == "COMPLETE":
                return receipt
            if not (folder / "remote-state.json").exists():
                raise ExperimentError("NO_PERSISTED_REMOTE_JOB")
        group = manifest["groups"][group_name]
        try:
            if arm == "A":
                receipt = run_project(run, folder, group, receipt)
                write(folder / "receipt.json", receipt)
                return receipt
            if token_file is None:
                raise ExperimentError("TOKEN_FILE_REQUIRED")
            token = token_file.read_text().strip()
            if not token or any(c.isspace() for c in token):
                raise ExperimentError("TOKEN_FORMAT_INVALID")
            if not resume:
                body = request_body(group_name, group, arm, receipt["data_id"])
                write(folder / "request.json", body)
                receipt["parse_submissions"] = 1
                write(folder / "receipt.json", receipt)
                with httpx.Client(
                    timeout=httpx.Timeout(120, connect=10), trust_env=False, follow_redirects=False
                ) as client:
                    result = api_call(client, folder, "POST", "/file-urls/batch", token, body)
                    data = result["data"]
                    remote = {"batch_id": data["batch_id"], "upload_url": data["file_urls"][0]}
                    write(folder / "remote-state.json", remote)
                    status = None
                    try:
                        input_path = run / "frozen" / group_name / "input.pdf"
                        with input_path.open("rb") as stream:
                            response = client.put(
                                remote_url(remote["upload_url"]),
                                content=stream,
                                headers={"Content-Length": str(input_path.stat().st_size)},
                            )
                        status = response.status_code
                        response.raise_for_status()
                    finally:
                        record_http(folder, "PUT", "official_upload_storage", status)
                receipt.update(status="PENDING_REMOTE", upload_status="UPLOADED")
                write(folder / "receipt.json", receipt)
            return collect(folder, token, timeout=timeout)
        except Exception as exc:
            receipt = read(folder / "receipt.json")
            has_remote = (folder / "remote-state.json").exists()
            receipt.update(
                status="PENDING_REMOTE" if has_remote else "FAILED",
                error=str(exc) if isinstance(exc, ExperimentError) else "TRANSPORT_OR_RUN_FAILED",
                error_type=type(exc).__name__,
                updated_at=now(),
            )
            if isinstance(exc, httpx.HTTPStatusError):
                receipt["http_status"] = exc.response.status_code
            write(folder / "receipt.json", receipt)
            return receipt
    finally:
        lock.unlink()
