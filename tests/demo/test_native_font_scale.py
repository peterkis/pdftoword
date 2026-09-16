"""Physical PDF text size must survive native conversion into editable Word runs."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
from docx import Document
from prototypes.docx_output.common import PRIVATE
from prototypes.docx_output.pipeline import convert
from tests.demo.synthetic import make_pdf


@pytest.mark.parametrize(
    "matrix,expected,graphics",
    [
        ("12 0 0 12", 12, ""),
        ("10 0 0 16", 16, ""),
        ("6 0 0 6", 12, "2 0 0 2 0 0 cm"),
        ("1 0 0 1", 1, ""),
    ],
)
def test_native_transformed_font_uses_page_points(
    tmp_path: Path, matrix: str, expected: int, graphics: str
) -> None:
    source = tmp_path / "scaled.pdf"
    encoded = "Scaled text".encode("utf-16-be").hex()
    make_pdf(
        source,
        decoration=(f"q {graphics} BT /F1 1 Tf {matrix} 60 300 Tm <{encoded}> Tj ET Q\n".encode()),
    )
    jobs = PRIVATE / ("font-size-test-" + uuid.uuid4().hex)
    try:
        job = convert(source, mode="native", output_root=jobs)
        paragraphs = [
            p for p in Document(str(job / "auto.docx")).paragraphs if p.text == "Scaled text"
        ]
        assert len(paragraphs) == 1
        sizes = [r.font.size.pt for r in paragraphs[0].runs if r.text.strip() and r.font.size]
        assert sizes and all(abs(size - expected) <= 0.5 for size in sizes)
    finally:
        if jobs.exists():
            shutil.rmtree(jobs)
