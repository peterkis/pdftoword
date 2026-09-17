"""Safe reports must reject hidden skips and never publish parametrized input or traceback."""

import json
from pathlib import Path

import pytest

from quality_results import publish_tests


@pytest.mark.parametrize('status', ['SKIP', 'XFAIL', 'XPASS', 'FAIL', 'ERROR'])
def test_unapproved_outcomes_fail_without_leaking_input(tmp_path: Path, status: str) -> None:
    nodeid = 'tests/unit/test_synthetic.py::test_case[PRIVATE_SENTINEL-/Users/private/source.pdf]'
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests/quality-skip-allowlist.json').write_text('[]')
    source = tmp_path / 'raw.json'
    source.write_text(json.dumps({'collected': [nodeid], 'exitstatus': 0, 'results': {
        nodeid: {'status': status, 'reason': 'PRIVATE_SENTINEL', 'duration_seconds': 0.1}
    }}))
    public = tmp_path / 'public'
    public.mkdir()
    summary, valid = publish_tests(source, public, tmp_path)
    assert not valid
    assert summary['counts'][status] == 1
    for path in public.iterdir():
        assert 'PRIVATE_SENTINEL' not in path.read_text()
        assert '/Users/' not in path.read_text()


def test_approved_platform_skip_is_counted(tmp_path: Path) -> None:
    import sys

    nodeid = 'tests/unit/test_permissions.py::test_mode'
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests/quality-skip-allowlist.json').write_text(json.dumps([
        {'nodeid': nodeid, 'platform': sys.platform, 'reason': 'POSIX_MODE_NOT_APPLICABLE'}
    ]))
    raw = {'collected': [nodeid], 'exitstatus': 0, 'results': {nodeid: {
        'status': 'SKIP', 'reason': 'POSIX_MODE_NOT_APPLICABLE', 'duration_seconds': 0.0
    }}}
    source = tmp_path / 'raw.json'
    source.write_text(json.dumps(raw))
    public = tmp_path / 'public'
    public.mkdir()
    summary, valid = publish_tests(source, public, tmp_path)
    assert valid
    assert summary['counts']['SKIP'] == 1


def test_empty_or_incomplete_reports_cannot_pass(tmp_path: Path) -> None:
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests/quality-skip-allowlist.json').write_text('[]')
    source = tmp_path / 'raw.json'
    source.write_text(json.dumps({'collected': [], 'results': {}, 'exitstatus': 0}))
    assert not publish_tests(source, tmp_path, tmp_path)[1]


@pytest.mark.parametrize('body', [
    'pytest.skip("unapproved")',
    'pytest.xfail("unapproved")',
])
def test_real_pytest_skips_cannot_turn_quality_green(tmp_path: Path, body: str) -> None:
    import os
    import subprocess
    import sys

    from quality import ROOT

    (tmp_path / 'test_outcome.py').write_text(
        'import pytest\ndef test_synthetic():\n    ' + body + '\n'
    )
    source = tmp_path / 'raw.json'
    result = subprocess.run([
        sys.executable, '-m', 'pytest', '-p', 'quality_pytest', '-q',
        '--quality-results', str(source),
    ], cwd=tmp_path, env={**os.environ, 'PYTHONPATH': str(ROOT / 'scripts')},
        capture_output=True, check=False, timeout=30)
    assert result.returncode == 0
    public = tmp_path / 'public'
    public.mkdir()
    assert not publish_tests(source, public, ROOT)[1]
