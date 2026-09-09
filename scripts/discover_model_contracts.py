"""T0015 CLI: parse arguments, invoke the core, print only non-sensitive status."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from model_contract_discovery import load_config, run_discovery


def main(argv: list[str] | None = None) -> int:
    """Run a Gate without a second implementation or printing private paths/content."""
    parser = argparse.ArgumentParser(description="T0015 reproducible model contract evidence")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--test-image", type=Path, required=True)
    parser.add_argument("--promote-artifacts", action="store_true")
    security = parser.add_mutually_exclusive_group(required=True)
    security.add_argument(
        "--confirm-no-auth",
        action="store_true",
        help="Operator confirms no API key is required and old value was unused",
    )
    security.add_argument(
        "--confirm-key-rotation",
        action="store_true",
        help="Operator confirms the old key is revoked and a new local key is set",
    )
    args = parser.parse_args(argv)
    try:
        result = run_discovery(
            load_config(),
            args.output_dir,
            args.test_image,
            args.promote_artifacts,
            confirmed_no_auth=args.confirm_no_auth,
            confirmed_key_rotation=args.confirm_key_rotation,
        )
    except (ValueError, OSError) as error:
        # OSError messages may contain local file paths; do not print exception strings.
        print(
            json.dumps(
                {"overall_status": "BLOCKED_PREFLIGHT", "error_category": type(error).__name__}
            )
        )
        return 1
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "overall_status": result["overall_status"],
                "services": {
                    name: value["contract_status"] for name, value in result["services"].items()
                },
            }
        )
    )
    return 0 if result["overall_status"] == "ACCEPTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
