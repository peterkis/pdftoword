"""Parent-side transport to the isolated deterministic DocVortex runtime."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .common import ROOT, DemoError, Json


def call_worker(payload: Json) -> Json:
    """Capture all source-bearing IPC privately; never forward worker stderr into logs."""
    default = ROOT / "tmp/docx-demo/docvortex-runtime/.venv"
    python = Path(
        os.environ.get(
            "P2W_DOCVORTEX_PYTHON",
            str(default / ("Scripts/python.exe" if os.name == "nt" else "bin/python")),
        )
    )
    if not python.is_file():
        raise DemoError("DOCVORTEX_RUNTIME_NOT_INSTALLED")
    try:
        completed = subprocess.run(
            [str(python), "-I", str(Path(__file__).with_name("docvortex_worker.py"))],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        result = json.loads(completed.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise DemoError("DOCVORTEX_WORKER_UNAVAILABLE") from exc
    if completed.returncode or not result.get("ok"):
        raise DemoError("DOCVORTEX_PUBLIC_CALL_FAILED:" + str(result.get("error_type", "unknown")))
    if result.get("pdfium_loaded"):
        raise DemoError("DOCVORTEX_PDFIUM_ISOLATION_FAILED")
    return dict(result)
