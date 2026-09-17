"""Run the same offline engineering checks locally and in CI; never install tools."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION = '3.12.13'
NODE_VERSION = 'v24.18.0'


@dataclass(frozen=True)
class Command:
    """A named check with a bounded execution time; not a user-supplied shell string."""

    name: str
    argv: tuple[str, ...]
    timeout: float = 600


def write_json(path: Path, value: Any) -> None:
    """Write UTF-8 metadata, excluding untrusted command output."""
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def run_commands(
    commands: list[Command], cwd: Path, logs: Path
) -> tuple[list[dict[str, Any]], int]:
    """Run real processes serially, retaining failures and continuing independent checks."""
    logs.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    overall = 0
    for command in commands:
        start = time.monotonic()
        code: int | None = None
        with (logs / f'{command.name}.txt').open('wb') as output:
            try:
                child = subprocess.run(
                    command.argv, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                    timeout=command.timeout, check=False, shell=False,
                    env={k: v for k, v in {**os.environ, "PYTHONUTF8": "1"}.items()
                         if k not in {"PYTEST_ADDOPTS", "PYTEST_PLUGINS"}},
                )
                code = child.returncode
                status = 'PASS' if code == 0 else 'FAIL'
                if code:
                    overall = max(overall, 1)
            except FileNotFoundError:
                status = 'TOOL_MISSING'
                overall = 2
            except subprocess.TimeoutExpired:
                status = 'TIMEOUT'
                overall = max(overall, 1)
            except KeyboardInterrupt:
                status = 'INTERRUPTED'
                overall = 130
            except OSError:
                status = 'EXECUTION_ERROR'
                overall = 2
        results.append({'name': command.name, 'status': status, 'returncode': code,
                        'duration_seconds': round(time.monotonic() - start, 3)})
        if overall == 130:
            break
    return results, overall


def preflight() -> tuple[dict[str, str], list[str]]:
    """Check required tools without installing them or contacting any endpoint."""
    versions = {'python': platform.python_version(), 'platform': sys.platform,
                'architecture': platform.machine()}
    for key in ('ImageOS', 'ImageVersion'):
        value = os.environ.get(key, '')
        if value and all(c.isalnum() or c in '.-_' for c in value):
            versions[key] = value
    errors = []
    if versions['python'] != PYTHON_VERSION:
        errors.append('PYTHON_VERSION_MISMATCH')
    for module in ('pytest', 'ruff', 'mypy', 'jsonschema'):
        try:
            versions[module] = importlib.metadata.version(module)
        except importlib.metadata.PackageNotFoundError:
            errors.append(module.upper() + '_MISSING')
    for name in ('node', 'git'):
        executable = shutil.which(name)
        if executable is None:
            errors.append(name.upper() + '_MISSING')
            continue
        try:
            result = subprocess.run([executable, '--version'], capture_output=True,
                                    text=True, encoding='utf-8', timeout=15, check=False)
            if result.returncode:
                errors.append(name.upper() + '_UNAVAILABLE')
            else:
                versions[name] = result.stdout.strip()
                if name == 'node' and versions[name] != NODE_VERSION:
                    errors.append('NODE_VERSION_MISMATCH')
        except (OSError, subprocess.TimeoutExpired):
            errors.append(name.upper() + '_UNAVAILABLE')
    return versions, errors


def source_identity(root: Path) -> dict[str, Any]:
    """Fingerprint tracked and task-source files without exposing local absolute paths."""
    def git(*args: str) -> str:
        return subprocess.check_output(['git', *args], cwd=root, text=True,
                                       encoding='utf-8', stderr=subprocess.DEVNULL).strip()
    try:
        commit = git('rev-parse', 'HEAD')
        dirty = bool(git('status', '--porcelain'))
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = 'UNAVAILABLE', True
    hashes = {}
    # Git's ignore rules exclude private runtime trees even when nested under scripts/tests.
    names = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
        cwd=root, text=True, encoding='utf-8', stderr=subprocess.DEVNULL,
    ).split('\0')
    for name in sorted(set(names)):
        if not name:
            continue
        relative = Path(name)
        path = root / relative
        is_source = (relative.parts[0] in {'scripts', 'tests', 'prototypes', 'packages',
                                           'specs', 'samples', '.github'}
                     and path.suffix in {'.py', '.json', '.yml', '.js', '.toml'})
        if (is_source or name in {'pyproject.toml', 'uv.lock'}) and (
            path.is_file() and not path.is_symlink()
        ):
            hashes[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {'commit': commit, 'dirty': dirty, 'source_sha256': hashes}


def default_commands(root: Path, private: Path) -> list[Command]:
    """Declare one command list used by both local and CI execution."""
    python = sys.executable
    return [
        Command('pytest', (python, '-m', 'pytest', 'tests', '-q',
                           '--junitxml', str(private / 'junit.xml'),
                           '--quality-results', str(private / 'tests.json'))),
        Command('ruff', (python, '-m', 'ruff', 'check', '.')),
        Command('mypy', (python, '-m', 'mypy', '.')),
        Command('task_catalog', (python, str(root / 'scripts/validate_task_catalog.py'))),
        Command('model_baseline', (python, str(root / 'scripts/validate_model_baseline.py'))),
        Command('schema_samples', (python, str(root / 'scripts/validate_schema_samples.py'))),
    ]


def prepare_output(output: Path) -> tuple[Path, Path]:
    """Refuse existing data and symlink paths; allocate private and public report directories."""
    if any(p.is_symlink() for p in (output, *output.parents)):
        raise ValueError('OUTPUT_SYMLINK')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('OUTPUT_NOT_EMPTY')
    output.mkdir(parents=True, exist_ok=True)
    private, public = output / 'private', output / 'public'
    private.mkdir(mode=0o700)
    public.mkdir()
    return private, public


def execute(output: Path) -> int:
    """Execute the complete gate and publish only structured safe reports."""
    from quality_results import publish_tests

    private, public = prepare_output(output)
    versions, errors = preflight()
    summary: dict[str, Any] = {'run_id': uuid.uuid4().hex, 'environment': versions,
                               'preflight_errors': errors, 'steps': [],
                               'model_requests': 0, 'status': 'ENVIRONMENT_ERROR'}
    code = 2
    if not errors:
        summary['source'] = source_identity(ROOT)
        summary['steps'], code = run_commands(default_commands(ROOT, private), ROOT, private)
        test_summary, valid = publish_tests(private / 'tests.json', public, ROOT)
        summary['tests'] = test_summary
        if not valid and code == 0:
            code = 1
        summary['status'] = ('PASS' if code == 0 else 'INTERRUPTED' if code == 130 else 'FAIL')
    summary['exit_code'] = code
    write_json(public / 'summary.json', summary)
    write_json(public / 'environment.json', versions)
    print(json.dumps({'status': summary['status'], 'exit_code': code,
                      'preflight_errors': errors}, ensure_ascii=False))
    return code


def main() -> int:
    """Run from any directory; reject invalid output settings without a traceback."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    output = args.output_dir or ROOT / 'tmp/quality' / uuid.uuid4().hex
    try:
        return execute(output.absolute())
    except (OSError, ValueError):
        print('QUALITY_CONFIGURATION_ERROR', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('QUALITY_INTERRUPTED', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
