"""Quality gates exercise real child processes without recursively running pytest."""

import json
import sys
from pathlib import Path

from quality import Command, run_commands


def test_failure_preserves_exit_code_and_runs_later_checks(tmp_path: Path) -> None:
    marker = tmp_path / 'after.txt'
    commands = [
        Command('failed', (sys.executable, '-c', 'raise SystemExit(7)')),
        Command('after', (sys.executable, '-c',
                          'from pathlib import Path; import sys; Path(sys.argv[1]).touch()',
                          str(marker))),
    ]
    results, code = run_commands(commands, tmp_path, tmp_path / 'logs')
    assert code == 1
    assert results[0]['returncode'] == 7
    assert results[0]['status'] == 'FAIL'
    assert results[1]['status'] == 'PASS'
    assert marker.exists()
    assert 'stdout' not in json.dumps(results)


def test_timeout_and_missing_program_are_not_success(tmp_path: Path) -> None:
    results, code = run_commands([
        Command('slow', (sys.executable, '-c', 'import time; time.sleep(5)'), timeout=0.05),
        Command('missing', (str(tmp_path / 'missing-tool'),)),
    ], tmp_path, tmp_path / 'logs')
    assert code == 2
    assert [r['status'] for r in results] == ['TIMEOUT', 'TOOL_MISSING']
    assert all(r['returncode'] is None for r in results)


def test_missing_node_fails_real_cli_without_running_checks(tmp_path: Path) -> None:
    import os
    import subprocess

    from quality import ROOT

    output = tmp_path / '中文 结果'
    env = {**os.environ, 'PATH': str(tmp_path)}
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/quality.py'),
                             '--output-dir', str(output)], cwd=tmp_path,
                            env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 2
    summary = json.loads((output / 'public/summary.json').read_text())
    assert 'NODE_MISSING' in summary['preflight_errors']
    assert summary['steps'] == []


def test_output_never_overwrites_existing_data(tmp_path: Path) -> None:
    import pytest

    from quality import prepare_output

    sentinel = tmp_path / 'keep.txt'
    sentinel.write_text('preserve')
    with pytest.raises(ValueError, match='OUTPUT_NOT_EMPTY'):
        prepare_output(tmp_path)
    assert sentinel.read_text() == 'preserve'


def test_parent_interruption_is_preserved(tmp_path: Path) -> None:
    import _thread
    import threading

    timer = threading.Timer(0.05, _thread.interrupt_main)
    timer.start()
    try:
        results, code = run_commands([
            Command('running', (sys.executable, '-c', 'import time; time.sleep(0.3)')),
            Command('never', (sys.executable, '-c', 'raise SystemExit(0)')),
        ], tmp_path, tmp_path / 'logs')
    finally:
        timer.join()
    assert code == 130
    assert len(results) == 1
    assert results[0]['status'] == 'INTERRUPTED'


def test_success_in_chinese_directory_keeps_output_private(tmp_path: Path) -> None:
    root = tmp_path / '中文 空格'
    root.mkdir()
    results, code = run_commands([
        Command('success', (sys.executable, '-c', 'print("PRIVATE_SENTINEL")')),
    ], root, root / 'logs')
    assert code == 0
    assert results[0]['returncode'] == 0
    assert 'PRIVATE_SENTINEL' not in json.dumps(results)
    assert 'PRIVATE_SENTINEL' in (root / 'logs/success.txt').read_text()


def test_source_fingerprint_excludes_ignored_runtime_files(tmp_path: Path) -> None:
    import subprocess

    from quality import source_identity

    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    (tmp_path / '.gitignore').write_text('tmp/\n*.raw.json\n')
    (tmp_path / 'scripts/tmp').mkdir(parents=True)
    (tmp_path / 'scripts/tool.py').write_text('"""Source."""\n')
    (tmp_path / 'scripts/tmp/private.raw.json').write_text('{"text":"PRIVATE_SENTINEL"}')
    (tmp_path / 'pyproject.toml').write_text('')
    (tmp_path / 'uv.lock').write_text('')
    result = source_identity(tmp_path)
    assert set(result['source_sha256']) == {'scripts/tool.py', 'pyproject.toml', 'uv.lock'}
