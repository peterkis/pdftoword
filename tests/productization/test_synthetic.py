"""Verify fault asset properties, not model quality or product acceptance."""

import json
from contextlib import closing
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-untyped]
import pytest
from PIL import Image
from tests.productization.synthetic.generate import generate

from product_dataset import reference_valid


def test_synthetic_assets_have_the_declared_faults(tmp_path: Path) -> None:
    root = tmp_path / "generated"
    rows = generate(root)
    assert len(rows) == 20
    with (
        pdfium.PdfDocument(root / "blank.pdf") as doc,
        closing(doc[0]) as page,
        closing(page.get_textpage()) as text,
    ):
        assert text.count_chars() == 0
    with pdfium.PdfDocument(root / "hidden.pdf") as doc, closing(doc[0]) as page:
        objects = list(page.get_objects())
        text_objects = [obj for obj in objects if obj.type == pdfium.raw.FPDF_PAGEOBJ_TEXT]
        assert len(text_objects) == 2
        assert any(pdfium.raw.FPDFTextObj_GetTextRenderMode(obj) == 3 for obj in text_objects)
    with pdfium.PdfDocument(root / "overlap.pdf") as doc, closing(doc[0]) as page:
        assert any(obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE for obj in page.get_objects())
    with pdfium.PdfDocument(root / "crop.pdf") as doc, closing(doc[0]) as page:
        assert page.get_cropbox() == (20, 30, 280, 380)
    for angle in (0, 90, 180, 270):
        with pdfium.PdfDocument(root / f"rotation-{angle}.pdf") as doc, closing(doc[0]) as page:
            assert page.get_rotation() == angle
    for name in ("damaged.pdf", "encrypted.pdf"):
        with pytest.raises(pdfium.PdfiumError):
            pdfium.PdfDocument(root / name)
    with pdfium.PdfDocument(root / "encrypted.pdf", password="synthetic-only") as doc:
        assert len(doc) == 1
    with Image.open(root / "transparent.png") as image:
        assert image.getchannel("A").getextrema() == (0, 0)
    assert not reference_valid("table", json.loads((root / "invalid-table.json").read_text()))
    with pytest.raises(json.JSONDecodeError):
        json.loads((root / "corrupt-cache.json").read_text())
    with pytest.raises(FileExistsError):
        generate(root)
