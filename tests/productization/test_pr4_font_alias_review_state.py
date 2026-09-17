"""Font aliases resolve independent of order, and reviewed manifests record imports."""

import json
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

from acceptance.metrics import evaluate
from product_acceptance import digest, import_reviewed


@pytest.mark.parametrize("case", ["forward", "reverse", "multi", "cycle", "benign"])
def test_font_alias_graph(tmp_path: Path, case: str) -> None:
    path, truth, sources = specimen(tmp_path)
    doc: Any = Document(str(path))
    doc.paragraphs[0].runs[0].font.name = "AliasA"
    doc.save(str(path))
    with zipfile.ZipFile(path) as archive:
        files = {n: archive.read(n) for n in archive.namelist()}
    root = etree.fromstring(files["word/fontTable.xml"])
    edges = (
        [("AliasA", "Blocked")]
        if case in {"forward", "reverse"}
        else [("AliasA", "AliasB"), ("AliasB", "Blocked")]
    )
    if case == "cycle":
        edges = [("AliasA", "AliasB"), ("AliasB", "AliasA")]
    elif case == "benign":
        edges = [("AliasA", "AliasB"), ("AliasB", "Arial")]
    nodes = []
    for name, alternate in edges:
        font, alias = OxmlElement("w:font"), OxmlElement("w:altName")
        font.set(qn("w:name"), name)
        alias.set(qn("w:val"), alternate)
        font.append(alias)
        nodes.append(font)
    if case != "benign":
        blocked = nodes[-1] if case == "cycle" else OxmlElement("w:font")
        if case != "cycle":
            blocked.set(qn("w:name"), "Blocked")
            nodes.append(blocked)
        charset = OxmlElement("w:charset")
        charset.set(qn("w:val"), "02")
        blocked.append(charset)
    root.extend(reversed(nodes) if case == "reverse" else nodes)
    files["word/fontTable.xml"] = etree.tostring(root)
    with zipfile.ZipFile(path, "w") as archive:
        for n, data in files.items():
            archive.writestr(n, data)
    result = evaluate(path, truth, sources)
    assert ("UNSUPPORTED_FONT_MAPPING" in result["errors"]) is (case != "benign")


def test_import_records_reviewed_state_without_claiming_acceptance(tmp_path: Path) -> None:
    bundle = tmp_path / "base"
    bundle.mkdir()
    base_bundle(bundle)
    run_path = bundle / "run.json"
    run = json.loads(run_path.read_text())
    run["reviewed"] = {"status": "NOT_RUN", "artifact": None}
    run_path.write_text(json.dumps(run))
    seal_path = bundle / "seal.json"
    seal = json.loads(seal_path.read_text())
    seal["run.json"] = digest(run_path)
    seal_path.write_text(json.dumps(seal))
    original = digest(run_path)
    output = tmp_path / "reviewed"
    result = import_reviewed(bundle, bundle / "auto.docx", output)
    imported_run = json.loads((output / "run.json").read_text())
    assert imported_run["revision"] == "reviewed"
    assert imported_run["reviewed"] == {"status": "IMPORTED", "artifact": "reviewed.docx"}
    assert result["human_acceptance"] == "PENDING"
    assert digest(run_path) == original
