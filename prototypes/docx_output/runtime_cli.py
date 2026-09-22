"""Installed local runtime entrypoint: native input and sealed offline exports only."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .common import JOBS, DemoError
from .runtime_queue import FINISHED, RuntimeQueue, error_code


def main() -> int:
    """Run a serialized operation or serve the existing private localhost review UI."""
    parser = argparse.ArgumentParser(
        description="PDF2Word 本地运行候选：native/离线重导出；表格保图、布局受限。"
    )
    parser.add_argument("--output-root", type=Path, default=JOBS)
    sub = parser.add_subparsers(dest="command", required=True)
    server = sub.add_parser("serve")
    server.add_argument("--port", type=int, default=8765)
    convert = sub.add_parser("convert")
    convert.add_argument("--input", type=Path, required=True)
    convert.add_argument("--pages", default="1")
    export = sub.add_parser("reexport")
    export.add_argument("--source-job", type=Path, required=True)
    export.add_argument("--revision", choices=["auto", "reviewed"], default="auto")
    export.add_argument("--style", type=Path)
    sub.add_parser("status")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            import uvicorn

            from .server import create_app

            uvicorn.run(
                create_app(args.port, args.output_root, runtime=True),
                host="127.0.0.1",
                port=args.port,
                log_level="warning",
                access_log=False,
            )
            return 0
        with RuntimeQueue(args.output_root, autostart=args.command != "status") as queue:
            if args.command == "status":
                print(json.dumps(queue.status(), ensure_ascii=False))
                return 0
            row = (
                queue.submit_native(args.input, args.pages)
                if args.command == "convert"
                else queue.submit_export(
                    args.source_job,
                    args.revision,
                    json.loads(args.style.read_text()) if args.style else None,
                )
            )
            while True:
                result = next(
                    r for r in queue.records() if r["operation_id"] == row["operation_id"]
                )
                if result["status"] in FINISHED:
                    if result["status"] in {"SUCCEEDED", "PARTIAL"}:
                        print(args.output_root / result["job_id"] / "auto.docx")
                        return 0
                    print(
                        json.dumps(
                            {
                                "status": result["status"],
                                "code": result.get("code"),
                                "operation_id": result["operation_id"],
                            }
                        )
                    )
                    return 1
                if queue.last_error:
                    raise DemoError(queue.last_error)
                time.sleep(0.1)
    except (OSError, DemoError) as exc:
        print(error_code(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
