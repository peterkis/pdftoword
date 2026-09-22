"""The real repository config skips runtime evidence but still checks live code."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_mypy_runtime_boundary_keeps_source_errors_visible(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    for directory in ("tmp/old-a", "tmp/old-b", "outputs/job", "artifacts/run", "data/jobs/one"):
        path = tmp_path / directory
        path.mkdir(parents=True)
        (path / "writer-before.py").write_text("this is not valid python!!!\n")
    for name in ("live.py", "tests/tmp/check_me.py", "scripts/smoke_models_extra.py"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('value: int = "must be checked"\n')
    (tmp_path / "scripts/smoke_models.py").write_text("legacy smoke fixture is not python!!!\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(root / "pyproject.toml"),
            "--no-incremental",
            "--cache-dir",
            str(tmp_path / ".mypy_cache"),
            ".",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Duplicate module" not in result.stdout
    assert "syntax" not in result.stdout
    for source_name in ("live.py", "tests/tmp/check_me.py", "scripts/smoke_models_extra.py"):
        assert f"{source_name}:1: error:" in result.stdout
    assert "Found 3 errors in 3 files" in result.stdout
