"""Inspect immutable Word exports and report source-bound geometry only when unambiguous."""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-untyped]
from lxml import etree

from .common import ARMS, GROUPS, Json, digest, offline, read, verify, write
from .evaluate import docx_units


def semantic_payload(path: Path) -> Json:
    """Compare text, actual math content and media before/after an undo/save cycle."""
    document = docx_units(path)
    with zipfile.ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        ns = {"m": "http://schemas.openxmlformats.org/officeDocument/2006/math"}
        math = root.xpath("//m:t/text()", namespaces=ns)
        media = sorted(
            hashlib.sha256(archive.read(n)).hexdigest()
            for n in archive.namelist()
            if n.startswith("word/media/")
        )
    return {
        "text": "".join(p["text"] for p in document["paragraphs"]),
        "math_text": math,
        "media_sha256": media,
        "inventory": document["inventory"],
    }


def audit_word(run: Path, evaluation: Path, output: Path, word_version: str) -> Json:
    """Only a real exported Word PDF establishes opened/rendered status, never a DOCX count."""
    with offline():
        verify(run / "frozen")
        manifest = read(run / "frozen/manifest.json")
        output.mkdir(parents=True, exist_ok=False)
        records = []
        for group, (_, original_pages, _) in GROUPS.items():
            for arm in ARMS:
                folder = run / "runs" / group / arm / "artifacts"
                original = folder / ("A.docx" if arm == "A" else "B.docx")
                if not original.exists():
                    records.append({"group": group, "arm": arm, "word_status": "NO_DOCX"})
                    continue
                verify(folder)
                label = f"{group}-{arm}"
                copy = run / "word-review" / f"{label}.docx"
                clean = run / "word-review" / f"{label}-clean.docx"
                if clean.exists():
                    copy = clean
                pdf = run / "word-review" / f"{label}.pdf"
                if clean.exists():
                    pdf = clean.with_suffix(".pdf")
                native_pdf = run / "word-review" / f"{label}-clean-native.pdf"
                if native_pdf.exists():
                    pdf = native_pdf
                base, restored = semantic_payload(original), semantic_payload(copy)
                equality = {
                    k: base[k] == restored[k] for k in ("text", "math_text", "media_sha256")
                }
                row: Json = {
                    "group": group,
                    "arm": arm,
                    "source_pages": len(original_pages),
                    "docx_sha256": digest(original),
                    "copy_sha256": digest(copy),
                    "copy_byte_identical": digest(copy) == digest(original),
                    "word_pdf": str(pdf.relative_to(run)),
                    "export_method": "Word local Save As PDF"
                    if pdf == native_pdf
                    else "Word Print to PDF",
                    "roundtrip": equality,
                    "word_status": "NOT_RUN",
                    "word_version": word_version,
                    "probe_files": [
                        p.name for p in (run / "word-review").glob(label + "*edited.docx")
                    ],
                    "agent_visual": "SEPARATE_REVIEW_REQUIRED",
                    "human_acceptance": "PENDING",
                }
                if not all(equality.values()):
                    row["word_status"] = "ROUNDTRIP_CHANGED_REVIEW_REQUIRED"
                elif pdf.exists():
                    doc = pdfium.PdfDocument(pdf)
                    texts = []
                    sizes = []
                    for i in range(len(doc)):
                        page = doc[i]
                        text = page.get_textpage()
                        texts.append(text.get_text_range())
                        sizes.append(list(page.get_size()))
                        text.close()
                        page.close()
                    row.update(
                        word_status="OPENED_AND_EXPORTED",
                        word_pages=len(doc),
                        word_page_sizes=sizes,
                        word_pdf_sha256=digest(pdf),
                        page_count_equal=len(doc) == len(original_pages),
                    )
                    alignments = []
                    score_file = evaluation / group / f"{arm}-scoring.json"
                    if score_file.exists():
                        for source_page in read(score_file)["pages"]:
                            for match in source_page["matches"]:
                                ref = match["reference"]
                                if match["status"] != "MATCHED" or ref["kind"] != "text":
                                    continue
                                needle = "".join(o["text"] for o in match["outputs"])
                                candidates = [
                                    (i, found.start())
                                    for i, text in enumerate(texts)
                                    if len(needle) >= 4
                                    for found in re.finditer(re.escape(needle), text)
                                ]
                                record: Json = {
                                    "anchor_id": ref["id"],
                                    "original_page": source_page["original_page"],
                                    "status": "ALIGNMENT_REVIEW",
                                    "candidate_word_pages": [i + 1 for i, _ in candidates],
                                }
                                if len(candidates) == 1:
                                    i, index = candidates[0]
                                    page = doc[i]
                                    tp = page.get_textpage()
                                    boxes = [
                                        tp.get_charbox(j)
                                        for j in range(index, index + len(needle))
                                        if j < tp.count_chars()
                                    ]
                                    if boxes:
                                        width, height = sizes[i]
                                        box = [
                                            min(b[0] for b in boxes),
                                            height - max(b[3] for b in boxes),
                                            max(b[2] for b in boxes),
                                            height - min(b[1] for b in boxes),
                                        ]
                                        source_size = manifest["groups"][group]["page_map"][
                                            source_page["input_page"] - 1
                                        ]["size_pt"]
                                        expected = ref["bbox"]
                                        record.update(
                                            status="BOUND",
                                            word_page=i + 1,
                                            word_bbox=box,
                                            normalized_top_left_delta=[
                                                box[0] / width - expected[0] / source_size[0],
                                                box[1] / height - expected[1] / source_size[1],
                                            ],
                                            page_assignment_equal=i + 1
                                            == source_page["input_page"],
                                        )
                                    tp.close()
                                    page.close()
                                alignments.append(record)
                    doc.close()
                    write(
                        output / f"{label}-geometry.json",
                        {
                            "alignments": alignments,
                            "limitation": (
                                "Only exact unique strings are located; "
                                "remaining units require review"
                            ),
                        },
                    )
                    row["geometry_bound_units"] = sum(a["status"] == "BOUND" for a in alignments)
                    row["geometry_review_units"] = sum(a["status"] != "BOUND" for a in alignments)
                records.append(row)
        result = {
            "records": records,
            "model_calls": 0,
            "word_export_method": "Per-record local export method; no physical printing",
            "warning": (
                "A has paper/margin warnings recorded separately; all acceptance remains pending"
            ),
        }
        write(output / "word-verification.json", result)
        return result
