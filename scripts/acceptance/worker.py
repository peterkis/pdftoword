"""Conversion-only child process: never receives a ground-truth path."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import runpy
import socket
import sys
import threading
import time
from pathlib import Path
from types import FrameType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    """Exercise the actual CLI or in-process HTTP upload with Internet sockets blocked."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--entry", choices=["cli", "api"], required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--pages", required=True)
    parser.add_argument("--jobs", type=Path, required=True)
    args = parser.parse_args()
    counts = {"pipeline_calls": 0, "network_attempts": 0}
    original_connect = socket.socket.connect

    def connect(sock: socket.socket, address: Any) -> Any:
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            counts["network_attempts"] += 1
            raise OSError("ACCEPTANCE_OFFLINE")
        return original_connect(sock, address)

    def profile(frame: FrameType, event: str, arg: Any) -> None:
        if (
            event == "call"
            and frame.f_code.co_name == "convert"
            and (Path(frame.f_code.co_filename) == ROOT / "prototypes/docx_output/pipeline.py")
        ):
            counts["pipeline_calls"] += 1

    socket.socket.connect = connect  # type: ignore[method-assign, assignment]
    socket.socket.connect_ex = connect  # type: ignore[method-assign, assignment]
    sys.setprofile(profile)
    threading.setprofile(profile)
    if args.entry == "cli":
        sys.argv = [
            "docx_demo.py",
            "convert",
            "--input",
            str(args.input),
            "--pages",
            args.pages,
            "--mode",
            "native",
            "--content-provider",
            "ovis-pp",
            "--output-root",
            str(args.jobs),
        ]
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            try:
                runpy.run_path(str(ROOT / "scripts/docx_demo.py"), run_name="__main__")
            except SystemExit as exc:
                if exc.code:
                    return int(exc.code)
        job = Path(stdout.getvalue().strip()).parent
    else:
        from fastapi.testclient import TestClient
        from prototypes.docx_output.server import create_app

        with TestClient(
            create_app(output_root=args.jobs), base_url="http://127.0.0.1:8765"
        ) as client:
            token = client.get("/api/session").json()["token"]
            with args.input.open("rb") as source:
                response = client.post(
                    "/api/upload",
                    headers={"origin": "http://127.0.0.1:8765", "x-demo-session": token},
                    files={"file": ("input.pdf", source, "application/pdf")},
                    data={"mode": "native", "pages": args.pages, "content_provider": "ovis-pp"},
                )
            response.raise_for_status()
            deadline = time.monotonic() + 120
            while True:
                status = client.get("/api/status").json()
                if not status["busy"]:
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError("UPLOAD_TIMEOUT")
                time.sleep(0.02)
            if not status.get("job_id"):
                raise ValueError("UPLOAD_CONVERSION_FAILED")
            job = args.jobs / status["job_id"]
            response = client.get(f"/api/download/{job.name}/auto")
            response.raise_for_status()
            if response.content != (job / "auto.docx").read_bytes():
                raise ValueError("DOWNLOAD_HASH_MISMATCH")
    sys.setprofile(None)
    threading.setprofile(None)
    print(json.dumps({"job": str(job), **counts}))
    return 0 if counts == {"pipeline_calls": 1, "network_attempts": 0} else 1


if __name__ == "__main__":
    raise SystemExit(main())
