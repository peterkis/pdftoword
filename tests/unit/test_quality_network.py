"""All attempted network operations are synthetic and blocked before transport."""

import asyncio
import socket
import subprocess
import sys
from pathlib import Path

import httpx
import pytest


@pytest.mark.parametrize('url', ['http://127.0.0.1:8080', 'http://localhost:9000',
                                'http://[::1]:8000', 'https://invalid.test'])
def test_sync_http_is_blocked(url: str) -> None:
    with pytest.raises(AssertionError, match='REAL_NETWORK_FORBIDDEN'):
        httpx.get(url)


def test_async_http_is_blocked_and_mock_transport_still_works() -> None:
    async def check() -> None:
        async with httpx.AsyncClient() as client:
            with pytest.raises(AssertionError, match='REAL_NETWORK_FORBIDDEN'):
                await client.get('http://127.0.0.1:8080')
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text='synthetic')
        )) as client:
            assert (await client.get('http://unit.test')).text == 'synthetic'
    asyncio.run(check())


@pytest.mark.parametrize('method', ['connect', 'connect_ex', 'sendto'])
def test_other_clients_cannot_bypass_socket_guard(method: str) -> None:
    with socket.socket() as sock, pytest.raises(AssertionError, match='REAL_NETWORK_FORBIDDEN'):
        if method == 'sendto':
            sock.sendto(b'synthetic', ('127.0.0.1', 8080))
        else:
            getattr(sock, method)(('127.0.0.1', 8080))


def test_socketpair_internal_plumbing_is_allowed() -> None:
    a, b = socket.socketpair()
    with a, b:
        a.send(b'x')
        assert b.recv(1) == b'x'


def test_collection_time_network_is_blocked(tmp_path: Path) -> None:
    import os

    from quality import ROOT

    (tmp_path / 'test_import.py').write_text(
        'import httpx\nhttpx.get("http://127.0.0.1:8080")\n'
    )
    result = subprocess.run([sys.executable, '-m', 'pytest', '-p', 'quality_pytest',
                             '--collect-only', '-q'], cwd=tmp_path, capture_output=True,
                            text=True, env={**os.environ, 'PYTHONPATH': str(ROOT / 'scripts')},
                            check=False, timeout=30)
    assert result.returncode == 2
    assert 'REAL_NETWORK_FORBIDDEN' in result.stdout


def test_direct_pytest_requires_node_instead_of_skipping(tmp_path: Path) -> None:
    import os

    from quality import ROOT

    (tmp_path / 'test_node.py').write_text('def test_handler(node):\n    assert node\n')
    result = subprocess.run([
        sys.executable, '-m', 'pytest', '-p', 'quality_pytest', '-q',
    ], cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False,
        env={**os.environ, 'PATH': str(tmp_path), 'PYTHONPATH': str(ROOT / 'scripts')})
    assert result.returncode == 1
    assert 'NODE_MISSING' in result.stdout
    assert 'skipped' not in result.stdout
