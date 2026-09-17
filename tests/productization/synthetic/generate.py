"""Self-authored faults; generated files never count as real corpus input."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


def pdf_bytes(stream: bytes, *, rotation: int = 0, crop: bool = False) -> bytes:
    """Build a minimal PDF with a standard font and intentionally selectable geometry."""
    page = (
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] /Rotate {rotation} "
        + ("/CropBox [20 30 280 380] " if crop else "")
        + "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        page.encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
    ]
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(
        f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )
    return bytes(result)


def generate(root: Path) -> list[dict[str, str]]:
    """Create a new independent fault set with exact hashes and declared expectations."""
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    text = b"BT /F1 14 Tf 30 340 Td (Synthetic content 12 < 34) Tj ET"
    pdfs = {
        "native.pdf": (pdf_bytes(text), "native_text"),
        "blank.pdf": (pdf_bytes(b""), "zero_characters"),
        "title.pdf": (pdf_bytes(b"BT /F1 24 Tf 30 340 Td (Synthetic title) Tj ET"), "title_only"),
        "crop.pdf": (pdf_bytes(text, crop=True), "nonzero_cropbox"),
        "hidden.pdf": (
            pdf_bytes(text + b"\nBT 3 Tr /F1 14 Tf 30 340 Td (Synthetic content 12 < 34) Tj ET"),
            "duplicate_invisible_text",
        ),
        "overlap.pdf": (
            pdf_bytes(
                text + b"\nq 250 0 0 30 25 330 cm BI /W 1 /H 1 /CS /RGB /BPC 8 "
                b"/F /AHx ID 0088ff> EI Q"
            ),
            "graphic_text_overlap",
        ),
        "damaged.pdf": (b"%PDF-1.7\nINTENTIONALLY_INCOMPLETE", "reject_unreadable"),
        "encrypted.pdf": (
            bytes.fromhex(
                json.loads((Path(__file__).parent / "encrypted-pdf.json").read_text())["hex"]
            ),
            "password_required",
        ),
    }
    for angle in (0, 90, 180, 270):
        pdfs[f"rotation-{angle}.pdf"] = (pdf_bytes(text, rotation=angle), f"rotation_{angle}")
    rows = []
    for name, (content, expected) in pdfs.items():
        (root / name).write_bytes(content)
        rows.append({"file": name, "expected": expected})
    Image.new("RGBA", (24, 24), (100, 20, 200, 0)).save(root / "transparent.png")
    rows.append({"file": "transparent.png", "expected": "alpha_zero"})
    payloads = {
        "text-faults.json": {
            "pua": "\ue001",
            "xml_control": "a\u0001b",
            "html": "<script>synthetic()</script>",
            "url": "https://invalid.test/never-fetch.png",
            "currency_math": "Cost $5 and $x^2$",
            "unicode_edit": "𠮷😀AB",
            "long_formula": "x+" * 500 + "x",
        },
        "invalid-table.json": {
            "rows": 1,
            "cols": 1,
            "cells": [{"row": 0, "col": 0, "rowspan": 2, "colspan": 1, "text": "synthetic"}],
        },
        "wrong-edge.json": {
            "from": "missing-figure",
            "to": "missing-question",
            "relation": "belongs_to",
        },
        "partial-request.json": {
            "requests": [
                {"provider": "ovis", "status": "COMPLETE"},
                {"provider": "pp", "status": "FAILED"},
            ]
        },
        "started-request.json": {"status": "STARTED", "expected": "OUTCOME_UNKNOWN_NO_RETRY"},
        "cross-job.json": {"relative_path": "../other-job/private.json"},
    }
    for name, value in payloads.items():
        (root / name).write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
        rows.append({"file": name, "expected": "fault_payload_not_product_acceptance"})
    (root / "corrupt-cache.json").write_text("{broken", encoding="utf-8")
    rows.append({"file": "corrupt-cache.json", "expected": "reject_json"})
    for row in rows:
        p = root / row["file"]
        p.chmod(0o600)
        row["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    (root / "catalog.json").write_text(
        json.dumps(
            {"source": "self_authored_synthetic", "real_dataset_eligible": False, "items": rows},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return rows
