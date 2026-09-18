"""Install only the hashed deterministic DocVortex POC slice in an isolated venv."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME = ROOT / "tmp/docx-demo/docvortex-runtime/.venv"


def main() -> int:
    """Dependency fetch is explicit and separate from offline worker execution."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    args = parser.parse_args()
    runtime = args.runtime.absolute()
    runtime.parent.mkdir(parents=True, exist_ok=True)
    if not (runtime / "pyvenv.cfg").exists():
        subprocess.run(["uv", "venv", "--python", sys.executable, str(runtime)], check=True)
    python = runtime / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run(
        [
            "uv",
            "pip",
            "sync",
            "--python",
            str(python),
            "--require-hashes",
            str(ROOT / "requirements/docvortex-poc.txt"),
        ],
        check=True,
    )
    print(python)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
