"""Single-user localhost UI with same-origin/session gates and registered asset access."""

from __future__ import annotations

import secrets
import shutil
import threading
import uuid
from collections.abc import Callable
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


def create_app(port: int = 8765, output_root: Path = JOBS) -> FastAPI:
    """Create one local session, one worker, and no permissive CORS policy."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
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
        response: Response = await call_next(request)
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
        response = JSONResponse({"token": token})
        response.set_cookie("demo_session", token, httponly=True, samesite="strict")
        return response

    @app.get("/api/status")
    def status() -> Json:
        snapshot = dict(state)
        if state["busy"] and output_root.exists():
            new = [p for p in output_root.glob("demo-*") if p.name not in state.get("previous", [])]
            if new:
                current = max(new, key=lambda p: p.stat().st_mtime)
                if (current / "state.json").is_file():
                    snapshot.update(read(current / "state.json"))
        snapshot.pop("previous", None)
        return snapshot

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
                DEFAULT_RUN, variant, repeat, output_root, data.get("content_provider", "ovis-pp")
            )
        )

    @app.post("/api/upload")
    async def upload(request: Request) -> Json:
        if lock.locked():
            raise HTTPException(409, "JOB_BUSY")
        form = await request.form(max_files=1, max_fields=10, max_part_size=MAX_BYTES)
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
                str(form.get("mode", "native")),
                str(form.get("pages", "")).strip() or None,
            )

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

            ir = apply_overrides(job, read(job / "layout.auto.json"), data)
            # Preserve every earlier override ledger before replacing the current revision.
            if (job / "overrides.json").exists():
                save(
                    job / "review-history" / f"{uuid.uuid4().hex}.json",
                    read(job / "overrides.json"),
                )
            finish(job, ir, "reviewed")
            save(job / "overrides.json", data)
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
