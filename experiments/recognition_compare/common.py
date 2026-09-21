"""Private, sealed evidence utilities for the fixed three-arm experiment."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from experiments.mineru_replacement.run_direct import (
    ExperimentError,
    digest,
    inspect_docx,
    inventory,
    offline,
    quiet_upstream,
    safe_path,
)

Json = dict[str, Any]
ROOT = Path(__file__).resolve().parents[2]
GROUPS = {
    "G1": ("mix", [2, 4], "ch"),
    "G2": ("native", list(range(1, 13)), "ch"),
    "G3": ("scan", [1, 2, *range(4, 11)], "ch"),
    "G4": ("supermix", [1, 2], "ch"),
    "G5": ("supermix", [3], "cyrillic"),
    "G6": ("supermix", [4, 5, 6], "ch"),
}
ARMS = {"A": "reconstruction-v2", "B": "pipeline", "C": "vlm"}
__all__ = [
    "ARMS",
    "GROUPS",
    "ROOT",
    "ExperimentError",
    "Json",
    "digest",
    "inspect_docx",
    "inventory",
    "offline",
    "quiet_upstream",
    "safe_path",
]


def now() -> str:
    """Return a timestamp, never infer execution from filesystem presence."""
    return datetime.now(UTC).isoformat()


def read(path: Path) -> Json:
    """Read private JSON; public errors never contain its contents."""
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ExperimentError("JSON_OBJECT_REQUIRED")
    return value


def write(path: Path, value: Any) -> None:
    """Atomic receipts; callers reserve immutable output directories exclusively."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temp.chmod(0o600)
    temp.replace(path)


def seal(directory: Path) -> None:
    """Seal artifacts before any renderer or evaluator reads them."""
    write(
        directory / "seal.json", {k: v for k, v in inventory(directory).items() if k != "seal.json"}
    )


def verify(directory: Path) -> None:
    """Verify exact contents including absence of added artifacts."""
    actual = {k: v for k, v in inventory(directory).items() if k != "seal.json"}
    if read(directory / "seal.json") != actual:
        raise ExperimentError("EVIDENCE_HASH_MISMATCH")


def source_identity() -> Json:
    """Freeze tracked sources plus new experiment sources without copying secrets."""
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    files = {n: digest(ROOT / n) for n in names if n and (ROOT / n).is_file()}
    for directory in ("experiments", "tests/experiments"):
        for p in (ROOT / directory).rglob("*.py"):
            files[p.relative_to(ROOT).as_posix()] = digest(p)
    return {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
        "files": files,
        "source_sha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
    }


def load_local_environment() -> None:
    """Read the project's existing local model settings without printing values."""
    file = ROOT / ".env.local"
    if file.exists():
        for line in file.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.removeprefix("export ").split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def frozen(run: Path) -> Json:
    """Reject changed source code/configuration or prepared input/reference evidence."""
    verify(run / "frozen")
    manifest = read(run / "frozen/manifest.json")
    if manifest["source_identity"] != source_identity():
        raise ExperimentError("IMPLEMENTATION_CHANGED_SINCE_FREEZE")
    return manifest
