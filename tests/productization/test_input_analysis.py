"""Real backend, continuous geometry, and auto routing regressions."""

from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path

import pytest
from prototypes.docx_output.common import PRIVATE, DemoError, read
from prototypes.docx_output.input_analysis import PageGeometry, inspect_document, inspect_page
from prototypes.docx_output.pipeline import convert
from tests.demo.synthetic import make_pdf
from tests.productization.synthetic.generate import pdf_bytes


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_crop_geometry_real_backend(tmp_path: Path, rotation: int) -> None:
    source = tmp_path / "中文 带框.pdf"
    source.write_bytes(
        pdf_bytes(b"BT /F1 14 Tf 30 340 Td (Title) Tj ET", crop=True, rotation=rotation)
    )
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    doc = inspect_document(source)
    observed = inspect_page(source, 0)
    g = doc.pages[0]
    assert g.visible_box == (20, 30, 280, 380)
    assert (
        g.to_point(20, 380) == {0: (0, 0), 90: (350, 0), 180: (260, 350), 270: (0, 260)}[rotation]
    )
    for point in ((20, 30), (280, 380), (31.3, 342.8)):
        assert g.to_pdf(*g.to_point(*point)) == pytest.approx(point, abs=0.5)
    assert observed.text_runs[0]["text"] == "Title"
    assert observed.text_runs[0]["geometry_verified"]
    assert before == hashlib.sha256(source.read_bytes()).hexdigest()


def test_bad_pdf_is_not_password_error(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"%PDF-1.7\nnot-a-document")
    with pytest.raises(DemoError, match="PDF_FORMAT_ERROR"):
        inspect_document(source)
    make_pdf(source)
    assert inspect_document(source).page_count == 1


def test_geometry_size_swaps() -> None:
    assert PageGeometry((10, 20, 110, 220), 90).width == 200


@pytest.mark.parametrize(
    "stream,expected", [(b"", "blank"), (b"BT /F1 24 Tf 30 340 Td (Only title) Tj ET", "native")]
)
def test_auto_blank_and_title(tmp_path: Path, stream: bytes, expected: str) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(pdf_bytes(stream))
    root = PRIVATE / ("auto-test-" + uuid.uuid4().hex)
    try:
        job = convert(source, mode="auto", output_root=root)
        plan = read(job / "route-plan.json")
        assert plan["pages"][0]["content_state"] == expected
        assert plan["request_budget"] == 0
        assert read(job / "qa.json")["execution_status"] == "COMPLETE"
        assert (job / "auto.docx").is_file()
    finally:
        if root.exists():
            shutil.rmtree(root)


@pytest.mark.parametrize("matrix", ["0 1 -1 0", "0 -1 1 0", "-1 0 0 -1"])
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_text_rotation_frame_roundtrip(tmp_path: Path, matrix: str, rotation: int) -> None:
    source = tmp_path / "rotated-run.pdf"
    source.write_bytes(
        pdf_bytes(f"BT /F1 12 Tf {matrix} 150 200 Tm (Rotated) Tj ET".encode(), rotation=rotation)
    )
    observed = inspect_page(source, 0)
    run = observed.text_runs[0]
    assert run["text"] == "Rotated" and run["geometry_verified"]
    # Independently compare to PDFium object ink geometry, allowing one em for font ascent.
    obj = next(o for o in observed.objects if o["type"] == 1)
    assert max(abs(a - b) for a, b in zip(run["bbox"], obj["bbox"], strict=True)) < 13


def test_failure_releases_mutex_for_another_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import concurrent.futures

    import pypdfium2 as pdfium  # type: ignore[import-untyped]
    from prototypes.docx_output.input_analysis import PDFIUM_LOCK

    source = tmp_path / "source.pdf"
    make_pdf(source)
    original = pdfium.PdfPage.get_bbox

    def fail(page: object) -> tuple[float, float, float, float]:
        raise RuntimeError("injected geometry failure")

    monkeypatch.setattr(pdfium.PdfPage, "get_bbox", fail)
    with pytest.raises(RuntimeError):
        inspect_document(source)
    monkeypatch.setattr(pdfium.PdfPage, "get_bbox", original)

    def work() -> int:
        with PDFIUM_LOCK:
            return inspect_document(source).page_count

    with concurrent.futures.ThreadPoolExecutor() as executor:
        assert executor.submit(work).result(timeout=3) == 1


@pytest.mark.parametrize("paint", [b"3 Tr", b"1 1 1 rg"])
def test_invisible_or_white_text_is_not_trusted(tmp_path: Path, paint: bytes) -> None:
    from prototypes.docx_output.page_classifier import classify_page

    source = tmp_path / "hidden.pdf"
    source.write_bytes(pdf_bytes(b"BT " + paint + b" /F1 14 Tf 30 340 Td (Hidden) Tj ET"))
    classified = classify_page(inspect_page(source, 0).record())
    assert classified["page_type"] == "unknown"
    assert classified["reason_codes"]


def test_password_is_separate_from_corruption(tmp_path: Path) -> None:
    import json

    fixture = Path(__file__).parent / "synthetic/encrypted-pdf.json"
    source = tmp_path / "encrypted.pdf"
    source.write_bytes(bytes.fromhex(json.loads(fixture.read_text())["hex"]))
    with pytest.raises(DemoError, match="PDF_PASSWORD_REQUIRED"):
        inspect_document(source)
