"""Frame placement, OPC root targets and evaluator provenance stay explicit."""

import shutil
import zipfile
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree
from tests.productization.test_acceptance_harness import specimen
from tests.productization.test_pr4_import_text import base_bundle

import product_acceptance
from acceptance.metrics import evaluate


@pytest.mark.parametrize("where", ["text", "math", "style"])
def test_frame_position_is_unsupported(tmp_path: Path, where: str) -> None:
    path, truth, sources = specimen(tmp_path)
    doc: Any = Document(str(path))
    props = doc.paragraphs[2 if where == "math" else 0]._p.get_or_add_pPr()
    if where == "style":
        props = doc.styles["Normal"]._element.get_or_add_pPr()
    frame = OxmlElement("w:framePr")
    frame.set(qn("w:x"), "31680")
    frame.set(qn("w:y"), "31680")
    props.append(frame)
    doc.save(str(path))
    result = evaluate(path, truth, sources)
    assert "UNSUPPORTED_TEXT_POSITION" in result["errors"]


@pytest.mark.parametrize("case", ["main", "image", "styles", "escape"])
def test_package_root_target(tmp_path: Path, case: str) -> None:
    path, truth, sources = specimen(tmp_path)
    with zipfile.ZipFile(path) as archive:
        files = {n: archive.read(n) for n in archive.namelist()}
    relfile = "_rels/.rels" if case in {"main", "escape"} else "word/_rels/document.xml.rels"
    root = etree.fromstring(files[relfile])
    kind = "officeDocument" if case in {"main", "escape"} else case
    rel = next(r for r in root if r.get("Type", "").endswith("/" + kind))
    original_target = rel.get("Target")
    assert original_target is not None
    rel.set(
        "Target",
        "/../word/document.xml"
        if case == "escape"
        else ("/word/document.xml" if case == "main" else "/word/" + original_target),
    )
    files[relfile] = etree.tostring(root)
    with zipfile.ZipFile(path, "w") as archive:
        for n, data in files.items():
            archive.writestr(n, data)
    result = evaluate(path, truth, sources)
    assert result["structure_status"] == ("FAIL" if case == "escape" else "PASS")


@pytest.mark.parametrize(
    "changed", ["scripts/product_acceptance.py", "specs/product-quality/result.schema.json"]
)
def test_evaluator_fingerprint_tracks_entry_and_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    base_bundle(bundle)
    source = tmp_path / "source"
    shutil.copytree(product_acceptance.ROOT / "scripts/acceptance", source / "scripts/acceptance")
    for relative in ["scripts/product_acceptance.py", "specs/product-quality/result.schema.json"]:
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(product_acceptance.ROOT / relative, target)
    monkeypatch.setattr(product_acceptance, "ROOT", source)
    first = product_acceptance.evaluate_only(bundle, tmp_path / "one.json")
    target = source / changed
    target.write_bytes(target.read_bytes() + b"\n")
    second = product_acceptance.evaluate_only(bundle, tmp_path / "two.json")
    assert first["evaluator_sha256"] != second["evaluator_sha256"]
    assert first["identity"] == second["identity"]
