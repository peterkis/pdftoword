"""Thin CLI for development-only T0016 raster regression."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import raster_regression as core


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, invoke the actual core, print a body-free status."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--source", type=Path, required=True)
    prepare.add_argument("--case-id", required=True)
    prepare.add_argument("--case-dir", type=Path, required=True)
    validate = commands.add_parser("validate-ground-truth")
    validate.add_argument("--case-dir", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--case-dir", type=Path, required=True)
    run.add_argument("--protocol", type=Path, required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--confirm-no-auth", action="store_true")
    run.add_argument("--confirm-local-quality-evidence", action="store_true")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--run-dir", type=Path, required=True)
    evaluate.add_argument("--ground-truth", type=Path, required=True)
    promote = commands.add_parser("promote")
    promote.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if hasattr(args, "case_dir"):
            core.require_storage(args.case_dir, "cases")
        if hasattr(args, "run_dir"):
            core.require_storage(args.run_dir, "runs")
        if hasattr(args, "output_dir"):
            core.require_storage(args.output_dir, "runs")
        if args.command == "prepare":
            data = core.prepare(args.source, args.case_id, args.case_dir)
            result = {"case_id": data["case_id"], "pixel_equivalence_verified": True}
        elif args.command == "validate-ground-truth":
            result = core.validate_ground_truth(args.case_dir)
        elif args.command == "run":
            result = core.run(
                args.case_dir,
                args.protocol,
                args.run_id,
                args.output_dir,
                confirm_no_auth=args.confirm_no_auth,
                confirm_local_quality_evidence=args.confirm_local_quality_evidence,
            )
        elif args.command == "evaluate":
            data = core.evaluate(args.run_dir, args.ground_truth)
            result = {"run_id": data["run_id"], "execution_status": data["execution_status"]}
        else:
            result = core.promote(args.run_dir)
    except (ValueError, OSError, KeyError, TypeError) as error:
        # Never print arbitrary errors that could contain private paths or content.
        code = (
            str(error)
            if isinstance(error, ValueError) and str(error).replace("_", "").isalnum()
            else "LOCAL_EVIDENCE_ERROR"
        )
        print(json.dumps({"status": "ERROR", "code": code}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("execution_status", "COMPLETE") == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
