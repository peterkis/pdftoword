"""Single-user localhost UI with same-origin/session gates and registered asset access."""

from __future__ import annotations

import json
import secrets
import shutil
import threading
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, nullcontext
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.datastructures import UploadFile
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .common import (
    JOBS,
    MAX_BYTES,
    PRIVATE,
    DemoError,
    Json,
    finish_preview,
    job_path,
    private_dir,
    prune_preview_assets,
    read,
    safe_path,
    save,
    validate_input,
)
from .pipeline import convert, finish, replay
from .render import render
from .replay import DEFAULT_RUN

STATIC = Path(__file__).parent / "static"


class EvidenceJSONResponse(JSONResponse):
    """Preserve isolated surrogate evidence as JSON escapes in API responses."""

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content, ensure_ascii=True, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")


class BodyLimit:
    """Bound upload bytes before multipart parsing, including chunked requests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        total = 0

        async def bounded() -> Message:
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > MAX_BYTES + 65536:
                raise HTTPException(413, "INPUT_SIZE_LIMIT")
            return message

        await self.app(scope, bounded, send)


def create_app(port: int = 8765, output_root: Path = JOBS, *, runtime: bool = False) -> FastAPI:
    """Create one local session, one worker, and no permissive CORS policy."""
    queue = None
    if runtime:
        from .runtime_queue import RuntimeQueue

        queue = RuntimeQueue(output_root)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if queue is not None:
                queue.close()

    app = FastAPI(
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        default_response_class=EvidenceJSONResponse,
    )
    app.add_middleware(BodyLimit)
    token = secrets.token_urlsafe(32)
    origin = f"http://127.0.0.1:{port}"
    lock = threading.Lock()
    state: Json = {"state": "准备", "busy": False, "job_id": None}

    @app.middleware("http")
    async def guard(request: Request, call_next: Any) -> Response:
        if request.headers.get("host") != f"127.0.0.1:{port}":
            return JSONResponse({"detail": "INVALID_HOST"}, status_code=403)
        supplied_origin = request.headers.get("origin")
        if supplied_origin and supplied_origin != origin:
            return JSONResponse({"detail": "INVALID_ORIGIN"}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "CROSS_SITE_REJECTED"}, status_code=403)
        if request.method not in {"GET", "HEAD"}:
            if supplied_origin != origin or not secrets.compare_digest(
                request.headers.get("x-demo-session", ""), token
            ):
                return JSONResponse({"detail": "SESSION_REQUIRED"}, status_code=403)
        elif (
            request.url.path.startswith("/api/")
            and request.url.path != "/api/session"
            and not secrets.compare_digest(request.cookies.get("demo_session", ""), token)
        ):
            return JSONResponse({"detail": "SESSION_REQUIRED"}, status_code=403)
        if (
            runtime
            and request.method == "POST"
            and (
                request.url.path == "/api/replay"
                or request.url.path.startswith("/api/route/")
                or request.url.path.startswith("/api/compare-renderers/")
                or request.url.path.startswith("/api/render/")
            )
        ):
            return JSONResponse({"detail": "RUNTIME_OFFLINE_SCOPE_ONLY"}, status_code=403)
        try:
            with (
                queue.exclusive_output()
                if queue is not None
                and request.method == "POST"
                and request.url.path.startswith(("/api/review/", "/api/preview/"))
                else nullcontext()
            ):
                response: Response = await call_next(request)
        except DemoError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; "
            "connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(DemoError)
    async def demo_error(request: Request, exc: DemoError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(OSError)
    async def io_error(request: Request, exc: OSError) -> JSONResponse:
        import errno

        code = {
            errno.ENOSPC: "DISK_FULL",
            errno.EACCES: "DIRECTORY_PERMISSION_DENIED",
            errno.EPERM: "FILE_LOCKED_OR_PERMISSION_DENIED",
        }.get(exc.errno or 0, "LOCAL_IO_FAILED")
        return JSONResponse({"detail": code}, status_code=409)

    @app.get("/")
    def index() -> HTMLResponse:
        return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))

    @app.get("/static/{name}")
    def static(name: str) -> FileResponse:
        if name not in {"app.js", "style.css"}:
            raise HTTPException(404)
        return FileResponse(STATIC / name)

    @app.get("/api/session")
    def session() -> JSONResponse:
        response = JSONResponse({"token": token, "runtime": runtime})
        response.set_cookie("demo_session", token, httponly=True, samesite="strict")
        return response

    @app.get("/api/status")
    def status() -> Json:
        if queue is not None:
            return queue.status()
        snapshot = dict(state)
        if state["busy"] and output_root.exists():
            new = [p for p in output_root.glob("demo-*") if p.name not in state.get("previous", [])]
            if new:
                current = max(new, key=lambda p: p.stat().st_mtime)
                if (current / "state.json").is_file():
                    snapshot.update(read(current / "state.json"))
        snapshot.pop("previous", None)
        return snapshot

    @app.post("/api/runtime/cancel/{operation_id}")
    def cancel_runtime(operation_id: str) -> Json:
        if queue is None:
            raise HTTPException(404)
        return queue.cancel(operation_id)

    @app.post("/api/runtime/retry/{operation_id}")
    def retry_runtime(operation_id: str) -> Json:
        if queue is None:
            raise HTTPException(404)
        return queue.retry(operation_id)

    @app.get("/api/jobs")
    def jobs() -> Json:
        return {
            "jobs": [
                p.name
                for p in sorted(
                    output_root.glob("demo-*"), key=lambda p: p.stat().st_mtime, reverse=True
                )
                if (p / "layout.auto.json").is_file() and not p.is_symlink()
            ]
        }

    def start(work: Callable[[], Path]) -> Json:
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "JOB_BUSY")
        state.update(
            state="准备",
            busy=True,
            job_id=None,
            previous=[p.name for p in output_root.glob("demo-*")],
        )

        def run() -> None:
            try:
                job = work()
                state.update(state="待复核", job_id=job.name)
            except Exception as exc:
                state.update(
                    state="失败",
                    code=str(exc) if isinstance(exc, DemoError) else type(exc).__name__,
                )
            finally:
                state["busy"] = False
                lock.release()

        threading.Thread(target=run, daemon=True).start()
        return {"accepted": True}

    @app.post("/api/replay")
    async def replay_job(request: Request) -> Json:
        data = await request.json()
        variant, repeat = data.get("variant", "jpg"), data.get("repeat_index", 1)
        if variant not in {"jpg", "png"} or not isinstance(repeat, int) or repeat < 1:
            raise DemoError("INVALID_REPLAY_SELECTION")
        return start(
            lambda: replay(
                DEFAULT_RUN,
                variant,
                repeat,
                output_root,
                data.get("content_provider", "ovis-pp"),
                output_profile=data.get("output_profile", "legacy"),
            )
        )

    @app.post("/api/replay-job/{job_id}")
    async def replay_existing_job(job_id: str, request: Request) -> Json:
        from .common import digest
        from .style_replay import export_style

        source = job_path(job_id, output_root)
        data = await request.json()
        revision = data.get("revision", "auto")
        if revision not in {"auto", "reviewed"}:
            raise DemoError("INVALID_REVISION")
        if data.get("output_profile") != "fidelity-v3.1":
            raise DemoError("UNKNOWN_OUTPUT_PROFILE")
        layout_file = source / f"layout.{revision}.json"
        ir = read(layout_file)
        source_hash = digest(layout_file)
        if queue is not None:
            return {"accepted": True, **queue.submit_export(source, revision)}
        return start(
            lambda: export_style(
                source,
                output_root,
                ir.get("planning", {}).get("profile_settings", {}),
                source_hash,
                output_profile="fidelity-v3.1",
                revision=revision,
            )
        )

    @app.post("/api/upload")
    async def upload(request: Request) -> Json:
        if lock.locked():
            raise HTTPException(409, "JOB_BUSY")
        form = await request.form(max_files=1, max_fields=11, max_part_size=MAX_BYTES)
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise DemoError("INPUT_MISSING")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".pdf", ".png", ".jpg", ".jpeg"}:
            raise DemoError("UNSUPPORTED_FORMAT")
        directory = PRIVATE / "uploads" / uuid.uuid4().hex
        private_dir(directory)
        source = directory / ("input" + suffix)
        try:
            total = 0
            try:
                with source.open("xb") as output:
                    source.chmod(0o600)
                    while chunk := await file.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_BYTES:
                            raise DemoError("INPUT_SIZE_LIMIT")
                        output.write(chunk)
            finally:
                await file.close()
            validate_input(source)
            mode, pages = (
                str(form.get("mode", "auto")),
                str(form.get("pages", "")).strip() or None,
            )

            if queue is not None:
                if mode != "native" or str(form.get("output_profile")) != "fidelity-v3.1":
                    raise DemoError("RUNTIME_OFFLINE_SCOPE_ONLY")
                if any(form.get(k) == "true" for k in ("allow_model_calls", "ovis", "monkey")):
                    raise DemoError("RUNTIME_OFFLINE_SCOPE_ONLY")
                result = queue.submit_native(source, pages)
                shutil.rmtree(directory)
                return {"accepted": True, **result}

            def convert_upload() -> Path:
                try:
                    return convert(
                        source,
                        pages,
                        mode,
                        output_root,
                        allow_model_calls=form.get("allow_model_calls") == "true",
                        confirm_no_auth=form.get("confirm_no_auth") == "true",
                        confirm_scan=form.get("confirm_scan") == "true",
                        content_provider=str(form.get("content_provider", "ovis-pp")),
                        auto_profile=str(form.get("auto_profile", "legacy_ovis_pp")),
                        output_profile=str(form.get("output_profile", "legacy")),
                        ovis=form.get("ovis") == "true",
                        monkey=form.get("monkey") == "true",
                    )
                finally:
                    shutil.rmtree(directory)

            return start(convert_upload)
        except BaseException:
            if directory.exists():
                shutil.rmtree(directory)
            raise

    @app.get("/api/route/{job_id}")
    def route_summary(job_id: str) -> Json:
        job = job_path(job_id, output_root)
        if not (job / "route-plan.json").is_file():
            return {"available": False}
        plan = read(job / "route-plan.json")
        result_pages = (
            read(job / "region-results.json")["pages"]
            if (job / "region-results.json").exists()
            else plan["pages"]
        )
        return {
            "available": True,
            "plan_hash": plan["plan_hash"],
            "request_budget": plan["request_budget"],
            "profile": plan["profile"],
            "layout_requests": (
                read(job / "layout-results.json")["tasks"]
                if (job / "layout-results.json").exists()
                else plan.get("layout_requests", [])
            ),
            "provider_aliases": plan["provider_aliases"],
            "status": plan["status"],
            "executed": (job / "route-execution.json").exists() or plan["job_id"] != job.name,
            "pages": [
                {
                    "page_index": p["page_index"],
                    "page_type": p["page_type"],
                    "content_state": p["content_state"],
                    "regions": [
                        {k: r[k] for k in ("region_id", "bbox", "route", "reason", "status")}
                        for r in p["regions"]
                    ],
                }
                for p in result_pages
            ],
        }

    @app.post("/api/route/{job_id}/execute")
    async def execute_route(job_id: str, request: Request) -> Json:
        from .route_plan import execute_routes, validate_plan

        body = await request.json()
        if not isinstance(body, dict):
            raise DemoError("ROUTE_REQUEST_OBJECT_REQUIRED")
        job = job_path(job_id, output_root)
        plan_hash, budget = body.get("plan_hash"), body.get("budget")
        if (
            not isinstance(plan_hash, str)
            or not isinstance(budget, int)
            or isinstance(budget, bool)
            or body.get("confirm_no_auth") is not True
        ):
            raise DemoError("EXPLICIT_MODEL_AUTHORIZATION_REQUIRED")
        validate_plan(job, plan_hash, budget)
        return start(lambda: execute_routes(job, plan_hash, budget, True))

    @app.post("/api/route/{job_id}/cancel")
    async def cancel_route(job_id: str) -> Json:
        job = job_path(job_id, output_root)
        save(job / "route-cancelled.json", {"cancelled": True})
        return {"cancelled": True}

    @app.get("/api/job/{job_id}")
    def job_data(job_id: str) -> Json:
        job = job_path(job_id, output_root)
        ir = read(job / "layout.auto.json")
        result = {"auto": ir, "qa": read(job / "qa.json"), "overrides": {"operations": []}}
        if (job / "layout.reviewed.json").exists():
            result["reviewed"] = read(job / "layout.reviewed.json")
            result["qa_reviewed"] = read(job / "qa.reviewed.json")
        if (job / "overrides.json").exists():
            result["overrides"] = read(job / "overrides.json")
        return result

    @app.get("/api/asset/{job_id}/{asset_id}")
    def asset(job_id: str, asset_id: str, revision: str = "auto") -> FileResponse:
        if revision not in {"auto", "reviewed", "preview"}:
            raise DemoError("INVALID_REVISION")
        job = job_path(job_id, output_root)
        ir = read(job / f"layout.{revision}.json")
        registry = {a["id"]: a["path"] for a in ir["assets"]}
        registry.update(
            {f"source-p{k}": v["image_path"] for k, v in ir["provenance"]["pages"].items()}
        )
        qa: Json = (
            {"render_status": "PENDING"}
            if revision == "preview"
            else read(job / ("qa.json" if revision == "auto" else "qa.reviewed.json"))
        )
        if qa["render_status"] == "RENDERED":
            registry.update(
                {
                    f"render-{n}": f"rendered/{revision}/page-{n}.png"
                    for n in range(1, qa["rendered_page_count"] + 1)
                }
            )
        if asset_id not in registry:
            raise HTTPException(404)
        return FileResponse(safe_path(job, registry[asset_id]))

    @app.get("/api/download/{job_id}/{revision}")
    def download(job_id: str, revision: str) -> FileResponse:
        if revision not in {"auto", "reviewed"}:
            raise HTTPException(404)
        job = job_path(job_id, output_root)
        return FileResponse(safe_path(job, revision + ".docx"), filename=revision + ".docx")

    @app.post("/api/compare-renderers/{job_id}")
    async def compare_job(job_id: str, request: Request) -> Json:
        from .render_replay import compare_renderers

        data = await request.json()
        if data.get("renderer_a", "legacy") != "legacy" or (
            data.get("renderer_b", "legacy") != "legacy"
        ):
            raise DemoError("UNKNOWN_RENDERER")
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "JOB_BUSY")
        try:
            comparison = compare_renderers(
                job_path(job_id, output_root),
                data.get("revision", "auto"),
                output_root,
                source_seal=(
                    job_path(data["source_seal_job_id"], output_root) / "comparison.json"
                    if data.get("source_seal_job_id")
                    else None
                ),
            )
            return {
                "comparison_id": comparison.name,
                "comparison": read(comparison / "comparison.json"),
            }
        finally:
            lock.release()

    @app.post("/api/preview/{job_id}")
    async def preview_job(job_id: str, request: Request) -> Json:
        job = job_path(job_id, output_root)
        data = await request.json()
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "JOB_BUSY")
        try:
            from .review import apply_overrides

            before = set((job / "assets").glob("*.png"))
            previous = (
                read(job / "layout.preview.json") if (job / "layout.preview.json").exists() else {}
            )
            candidates = {job / a["path"] for a in previous.get("assets", [])}
            try:
                ir = apply_overrides(job, read(job / "layout.auto.json"), data)
                save(job / "layout.preview.json", ir)
            finally:
                candidates.update(set((job / "assets").glob("*.png")) - before)
                prune_preview_assets(job, candidates)
        finally:
            lock.release()
        return {"layout": ir}

    @app.post("/api/review/{job_id}")
    async def review_job(job_id: str, request: Request) -> Json:
        job = job_path(job_id, output_root)
        data = await request.json()
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "JOB_BUSY")
        try:
            from .review import apply_overrides

            previous = (
                read(job / "layout.reviewed.json")
                if (job / "layout.reviewed.json").exists()
                else {}
            )
            old_assets = {job / a["path"] for a in previous.get("assets", [])}
            ir = apply_overrides(job, read(job / "layout.auto.json"), data)
            # Preserve every earlier override ledger before replacing the current revision.
            if (job / "overrides.json").exists():
                save(
                    job / "review-history" / f"{uuid.uuid4().hex}.json",
                    read(job / "overrides.json"),
                )
            for name in ("~$reviewed.docx", "~$viewed.docx"):
                if (job / name).exists():
                    raise DemoError("WORD_DOCUMENT_OPEN_CLOSE_AND_RETRY")
            finish(job, ir, "reviewed")
            save(job / "overrides.json", data)
            finish_preview(job)
            prune_preview_assets(job, old_assets)
        finally:
            lock.release()
        return {"saved": True, "revision": "reviewed"}

    @app.post("/api/render/{job_id}")
    async def render_job(job_id: str, request: Request) -> Json:
        job = job_path(job_id, output_root)
        data = await request.json()

        def work() -> Path:
            render(job, data.get("revision", "auto"))
            return job

        return start(work)

    return app
