"""Thin CLI for DEMO-001's shared local pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prototypes.docx_output.common import JOBS, DemoError, job_path
from prototypes.docx_output.pipeline import convert, export, replay
from prototypes.docx_output.render import render
from prototypes.docx_output.replay import DEFAULT_RUN


def main() -> int:
    """Parse user authorization and report only actual local output paths."""
    parser = argparse.ArgumentParser(description="DEMO-001 本机输出验证原型")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("replay")
    r.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    r.add_argument("--variant", choices=["jpg", "png"], default="jpg")
    r.add_argument("--repeat-index", type=int, default=1)
    r.add_argument("--output-root", type=Path, default=JOBS)
    r.add_argument("--content-provider", choices=["ovis", "ovis-pp", "pp"], default="ovis-pp")
    c = sub.add_parser("convert")
    c.add_argument("--input", type=Path, required=True)
    c.add_argument("--content-provider", choices=["ovis", "ovis-pp", "pp"], default="ovis-pp")
    c.add_argument("--pages")
    c.add_argument("--mode", choices=["native", "raster"], required=True)
    c.add_argument("--output-root", type=Path, default=JOBS)
    for flag in [
        "allow-model-calls",
        "confirm-no-auth",
        "confirm-scan",
        "ovis",
        "monkey",
        "synthetic",
    ]:
        c.add_argument("--" + flag, action="store_true")
    for command in ("render", "export"):
        p = sub.add_parser(command)
        p.add_argument("--job-id", required=True)
        p.add_argument("--output-root", type=Path, default=JOBS)
        p.add_argument(
            "--revision",
            choices=["auto", "reviewed"],
            default="auto" if command == "render" else "reviewed",
        )
    s = sub.add_parser("serve")
    s.add_argument("--host", choices=["127.0.0.1"], default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        if args.command == "serve":
            import uvicorn
            from prototypes.docx_output.server import create_app

            uvicorn.run(create_app(args.port), host=args.host, port=args.port, access_log=False)
        elif args.command == "replay":
            job = replay(
                args.run_dir,
                args.variant,
                args.repeat_index,
                args.output_root,
                args.content_provider,
            )
            print((job / "auto.docx").resolve())
        elif args.command == "convert":
            job = convert(
                args.input,
                args.pages,
                args.mode,
                args.output_root,
                args.allow_model_calls,
                args.confirm_no_auth,
                args.ovis,
                args.monkey,
                args.confirm_scan,
                args.synthetic,
                args.content_provider,
            )
            print((job / "auto.docx").resolve())
        elif args.command == "render":
            qa = render(job_path(args.job_id, args.output_root), args.revision)
            print(qa["render_status"])
        elif args.command == "export":
            print(export(job_path(args.job_id, args.output_root), args.revision).resolve())
    except (DemoError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
