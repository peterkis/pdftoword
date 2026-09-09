"""Unit tests fail if they accidentally use a real HTTP transport."""

from __future__ import annotations

import httpx
import pytest


@pytest.fixture(autouse=True)
def prohibit_real_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """MockTransport remains available; pytest cannot send model HTTP requests."""

    def blocked(_self: httpx.HTTPTransport, _request: httpx.Request) -> httpx.Response:
        raise AssertionError("Real HTTP is forbidden in default pytest")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
