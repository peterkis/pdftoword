"""Boundary guards: importing the core package must stay SDK-free.

T0001 requires that the domain layer never depends on model SDKs, HTTP
clients or UI frameworks. These tests run the import in a fresh
interpreter so that pytest's own import graph cannot mask a violation.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pdf2word_core_domain
from pdf2word_core_domain import image_normalization, raster_io

# Modules that must never be pulled in (directly or transitively) by the
# core domain package.
FORBIDDEN_MODULES = frozenset(
    {
        "openai",
        "httpx",
        "requests",
        "aiohttp",
        "urllib3",
        "paddle",
        "paddleocr",
        "torch",
        "transformers",
        "vllm",
        "onnxruntime",
        "pypdfium2",
        "fitz",
    }
)


def test_package_exposes_version() -> None:
    assert pdf2word_core_domain.__version__


def test_import_does_not_load_model_sdks() -> None:
    # Compare sys.modules before/after the import so that modules the
    # runtime preloaded (sitecustomize, IDE injection, telemetry, distro
    # defaults) do not cause false failures; only modules newly pulled
    # in by the core package count as violations.
    code = (
        "import json, sys\n"
        f"forbidden = set({sorted(FORBIDDEN_MODULES)!r})\n"
        "before = set(sys.modules)\n"
        "import pdf2word_core_domain\n"
        "newly_loaded = (set(sys.modules) - before) & forbidden\n"
        "print(json.dumps(sorted(newly_loaded)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert json.loads(result.stdout) == []


def test_placeholder_modules_are_reserved_only() -> None:
    for module in (raster_io, image_normalization):
        assert module.__doc__, f"{module.__name__} must document its future scope"
        public_callables = [
            name
            for name, value in vars(module).items()
            if not name.startswith("_") and callable(value)
        ]
        assert public_callables == [], (
            f"{module.__name__} must stay an empty placeholder in T0001, "
            f"found: {public_callables}"
        )
