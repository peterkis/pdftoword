"""Fixed three-arm experiment CLI. All artifacts stay in a new private run directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.recognition_compare.common import ARMS, GROUPS, ExperimentError


def main() -> int:
    """Keep source payloads, credentials and signed URLs out of console output."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--edits", type=Path, required=True)
    sub.add_parser("extend-page-limit").add_argument("--previous-run", type=Path, required=True)
    for name in ("run", "resume"):
        p = sub.add_parser(name)
        p.add_argument("--arm", choices=ARMS, required=True)
        p.add_argument("--group", choices=GROUPS, required=True)
        p.add_argument("--token-file", type=Path)
        p.add_argument("--poll-timeout", type=int, default=1800)
    sub.add_parser("evaluate").add_argument("--output", type=Path, required=True)
    p = sub.add_parser("report")
    p.add_argument("--evaluation", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    for p in sub.choices.values():
        p.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            from experiments.recognition_compare.prepare import prepare

            result = prepare(args.dataset, args.edits, args.run_dir)
            print(
                json.dumps(
                    {
                        "status": "PREPARED",
                        "groups": len(result["groups"]),
                        "A_budget": result["A_total_budget"],
                    }
                )
            )
        elif args.command == "extend-page-limit":
            from experiments.recognition_compare.prepare import extend_page_limit

            result = extend_page_limit(args.previous_run, args.run_dir)
            print(
                json.dumps(
                    {"status": "PREPARED", "budget": result["amendment"]["new_request_budget"]}
                )
            )
        elif args.command in {"run", "resume"}:
            from experiments.recognition_compare.runner import execute

            result = execute(
                args.run_dir,
                args.arm,
                args.group,
                args.token_file,
                args.command == "resume",
                args.poll_timeout,
            )
            print(
                json.dumps(
                    {k: result.get(k) for k in ("status", "arm", "group", "error", "model_calls")}
                )
            )
            return 0 if result["status"] in {"COMPLETE", "PARTIAL"} else 1
        elif args.command == "evaluate":
            from experiments.recognition_compare.evaluate import evaluate

            result = evaluate(args.run_dir, args.output)
            print(
                json.dumps({"status": "EVALUATED", "rows": len(result["rows"]), "model_calls": 0})
            )
        elif args.command == "report":
            from experiments.recognition_compare.report import report

            report(args.run_dir, args.evaluation, args.output)
            print(json.dumps({"status": "REPORT_CREATED", "model_calls": 0}))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error": str(exc) if isinstance(exc, ExperimentError) else type(exc).__name__,
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
