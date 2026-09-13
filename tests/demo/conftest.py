"""Each test owns a fresh private directory; no user job is reused or removed."""

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from prototypes.docx_output.common import PRIVATE, private_dir


@pytest.fixture
def private_case() -> Iterator[Path]:
    path = PRIVATE / "tests" / uuid.uuid4().hex
    private_dir(path)
    try:
        yield path
    finally:
        shutil.rmtree(path)
