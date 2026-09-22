"""Local-only child runner. Receipts commit last; no terminal body output or network."""

from __future__ import annotations

import os
import resource
import site
import socket
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if os.environ.get("P2W_RUNTIME_SITE"):
    site.addsitedir(os.environ["P2W_RUNTIME_SITE"])
sys.path[:0] = [str(ROOT), str(ROOT / "scripts"), str(ROOT / "packages/core-domain/src")]


NETWORK_ATTEMPTS = 0


def denied(*args: Any, **kwargs: Any) -> Any:
    global NETWORK_ATTEMPTS
    NETWORK_ATTEMPTS += 1
    raise RuntimeError("RUNTIME_NETWORK_DISABLED")


def main() -> int:
    from prototypes.docx_output.common import digest, read, safe_path, save
    from prototypes.docx_output.runtime_queue import error_code

    started = time.monotonic()
    request_path = Path(sys.argv[1])
    request = read(request_path)
    root = Path(os.environ["P2W_RUNTIME_ROOT"])
    details = request["details"]
    socket.socket.connect = denied  # type: ignore[method-assign]
    socket.socket.connect_ex = denied  # type: ignore[method-assign]
    socket.create_connection = denied
    try:
        if request["kind"] == "native":
            from prototypes.docx_output.pipeline import convert

            source = safe_path(root, details["source"])
            if digest(source) != details["input_sha256"]:
                raise ValueError("INPUT_SEAL_MISMATCH")
            job = convert(
                source,
                details["pages"],
                "native",
                root,
                output_profile="fidelity-v3.1",
                page_limit=3,
            )
        elif request["kind"] == "export":
            from prototypes.docx_output.style_replay import export_style

            source = safe_path(root, details["source"])
            for name, sha in details["source_files"].items():
                if digest(safe_path(source, name)) != sha:
                    raise ValueError("SOURCE_SEAL_MISMATCH")
            job = export_style(
                source,
                root,
                details["style"],
                details["layout_sha256"],
                output_profile="fidelity-v3.1",
                revision=details["revision"],
            )
        else:
            raise ValueError("RUNTIME_OPERATION_UNSUPPORTED")
        ir = read(job / "layout.auto.json")
        qa = read(job / "qa.json")
        actual = {p["page_index"] + 1 for p in ir["pages"]}
        missing = sorted(set(details["requested_pages"]) - actual)
        names = (
            {"auto.docx", "layout.auto.json", "qa.json", "source-map.auto.json"}
            | {a["path"] for a in ir["assets"]}
            | {p["image_path"] for p in ir["provenance"]["pages"].values()}
        )
        receipt = {
            "job_id": job.name,
            "status": "PARTIAL"
            if missing or qa["execution_status"] in {"PARTIAL", "DEMO_OUTPUT_INSUFFICIENT"}
            else "SUCCEEDED",
            "missing_pages": missing,
            "model_call_count": 0,
            "network_attempts_observed": NETWORK_ATTEMPTS,
            "elapsed_seconds": time.monotonic() - started,
            "peak_rss_platform_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "peak_rss_scope": "local worker only; bytes on macOS",
            "files": {p: digest(safe_path(job, p)) for p in names},
        }
        if ir["metrics"].get("model_call_count", 0) != 0:
            raise ValueError("UNEXPECTED_MODEL_CALL")
        save(request_path.with_name("receipt.json"), receipt)
    except Exception as exc:
        with suppress(OSError):
            save(request_path.with_name("failure.json"), {"code": error_code(exc)})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
