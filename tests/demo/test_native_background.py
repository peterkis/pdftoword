"""Only source-equivalent white backings can stop producing duplicate crops."""

from __future__ import annotations

import gc
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium  # type: ignore[import-untyped]
import pytest
from prototypes.docx_output.common import digest
from prototypes.docx_output.input_analysis import inspect_page
from prototypes.docx_output.native_background import neutral_backgrounds
from tests.demo.synthetic import make_pdf


def source(path: Path, foreground: bool = False) -> None:
    text = "Header".encode("utf-16-be").hex()
    paint = "1 g 60 300 180 30 re f 0 g"
    label = f"BT /F1 10 Tf 70 310 Td <{text}> Tj ET"
    make_pdf(
        path, decoration=("\n".join([label, paint] if foreground else [paint, label])).encode()
    )


def test_background_equivalence_and_handle_cleanup(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pdf = tmp_path / "backing.pdf"
    source(pdf)
    before = digest(pdf)
    o = inspect_page(pdf, 0)
    for _ in range(3):
        proof = neutral_backgrounds(pdf, 0, list(o.objects), o.glyph_evidence, [])
        assert proof["status"] == "VERIFIED_NO_PIXEL_CONTRIBUTION"
        assert len(proof["path_ids"]) == 1 and len(proof["native_run_ids"]) == 1
        assert all(x["identical"] for x in proof["renders"])
    gc.collect()
    assert digest(pdf) == before
    assert "still open" not in capsys.readouterr().err


def test_foreground_white_is_never_ignored(tmp_path: Path) -> None:
    pdf = tmp_path / "mask.pdf"
    source(pdf, True)
    o = inspect_page(pdf, 0)
    assert not neutral_backgrounds(pdf, 0, list(o.objects), o.glyph_evidence, [])["path_ids"]


def test_pixel_mismatch_keeps_original_strategy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "backing.pdf"
    source(pdf)
    o = inspect_page(pdf, 0)
    original = pdfium.PdfPage.render
    calls = 0

    def changed(page: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        bitmap = original(page, *args, **kwargs)
        calls += 1
        if calls > 2:
            bitmap.buffer[0] ^= 1
        return bitmap

    monkeypatch.setattr(pdfium.PdfPage, "render", changed)
    proof = neutral_backgrounds(pdf, 0, list(o.objects), o.glyph_evidence, [])
    assert proof["status"] == "BACKGROUND_HAS_VISIBLE_EFFECT" and not proof["path_ids"]


def test_optional_proof_failure_keeps_original_strategy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "backing.pdf"
    source(pdf)
    o = inspect_page(pdf, 0)

    def failure(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("diagnostic renderer unavailable")

    monkeypatch.setattr(pdfium.PdfPage, "render", failure)
    proof = neutral_backgrounds(pdf, 0, list(o.objects), o.glyph_evidence, [])
    assert proof["status"] == "BACKGROUND_PROOF_UNAVAILABLE" and not proof["path_ids"]
