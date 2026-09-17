"""Session-wide offline policy and minimal test metadata for the quality entrypoint."""

from __future__ import annotations

import json
import socket
import subprocess
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest

from quality import NODE_VERSION

_PATCH = pytest.MonkeyPatch()
_RESULTS: dict[str, dict[str, Any]] = {}
_COLLECTED: list[str] = []
_PAIR = threading.local()


def pytest_addoption(parser: pytest.Parser) -> None:
    """Optional private metadata destination; normal pytest remains directly usable."""
    parser.addoption('--quality-results', help='Private machine-readable test results')


def pytest_configure(config: pytest.Config) -> None:
    """Install the policy before collection, including for import-time network attempts."""
    _RESULTS.clear()
    _COLLECTED.clear()

    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError('REAL_NETWORK_FORBIDDEN')

    async def async_blocked(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError('REAL_NETWORK_FORBIDDEN')

    _PATCH.setattr(httpx.HTTPTransport, 'handle_request', blocked)
    _PATCH.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', async_blocked)
    for method in ('connect', 'connect_ex', 'sendto', 'sendmsg'):
        original = getattr(socket.socket, method, None)
        if original is None:
            continue

        def guarded(self: socket.socket, *args: Any, _original: Any = original,
                    **kwargs: Any) -> Any:
            if (self.family in (socket.AF_INET, socket.AF_INET6)
                    and not getattr(_PAIR, 'active', False)):
                raise AssertionError('REAL_NETWORK_FORBIDDEN')
            return _original(self, *args, **kwargs)

        _PATCH.setattr(socket.socket, method, guarded)
    original_pair = socket.socketpair

    def socketpair(*args: Any, **kwargs: Any) -> Any:
        # Windows stdlib may emulate socketpair using an internal loopback connection.
        # Only that synchronous stdlib call, on this thread, gets the narrow exemption.
        _PAIR.active = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            _PAIR.active = False

    _PATCH.setattr(socket, 'socketpair', socketpair)
    _PATCH.setattr(socket, 'getaddrinfo', blocked)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Restore process globals once pytest has finished."""
    _PATCH.undo()


def pytest_collection_finish(session: pytest.Session) -> None:
    """Keep full IDs only in the private report for coverage comparison."""
    _COLLECTED.extend(item.nodeid for item in session.items)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Record outcomes without copying assertion messages, stdout or test data."""
    status = None
    reason = ''
    if report.failed:
        status = 'FAIL' if report.when == 'call' else 'ERROR'
    elif report.skipped:
        status = 'XFAIL' if hasattr(report, 'wasxfail') else 'SKIP'
        if isinstance(report.longrepr, tuple):
            text = str(report.longrepr[2])
            for known in ('POSIX_MODE_NOT_APPLICABLE', 'WINDOWS_SYMLINK_PRIVILEGE_UNAVAILABLE'):
                if text == 'Skipped: ' + known:
                    reason = known
    elif report.when == 'call':
        status = 'XPASS' if hasattr(report, 'wasxfail') else 'PASS'
    if status:
        previous = _RESULTS.get(report.nodeid)
        if previous and previous['status'] in {'FAIL', 'ERROR'} and status == 'PASS':
            return
        _RESULTS[report.nodeid] = {'status': status, 'reason': reason,
                                   'duration_seconds': round(report.duration, 6)}


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Write private results even if collection or execution failed."""
    target = session.config.getoption('--quality-results')
    if target:
        Path(target).write_text(json.dumps({'collected': _COLLECTED, 'results': _RESULTS,
                                           'exitstatus': int(exitstatus)}, indent=2) + '\n',
                                encoding='utf-8')


@pytest.fixture(scope='session')
def node() -> str:
    """Browser handler tests require the same pinned Node as the complete quality gate."""
    import shutil

    executable = shutil.which('node')
    if executable is None:
        pytest.fail('NODE_MISSING', pytrace=False)
    result = subprocess.run([executable, '--version'], capture_output=True, text=True,
                            encoding='utf-8', timeout=15, check=False)
    if result.returncode or result.stdout.strip() != NODE_VERSION:
        pytest.fail('NODE_VERSION_MISMATCH', pytrace=False)
    return executable
