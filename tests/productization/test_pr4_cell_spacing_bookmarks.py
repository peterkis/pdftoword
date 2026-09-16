"""Spacing expansion and malformed bookmark ancestry cannot pass provenance checks."""
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from tests.productization.test_acceptance_harness import specimen

from acceptance.metrics import evaluate


@pytest.mark.parametrize("where", ["table", "row", "style"])
@pytest.mark.parametrize("width", ["0", "31680"])
def test_cell_spacing(tmp_path: Path, where: str, width: str) -> None:
    path, truth, sources = specimen(tmp_path)
    doc: Any = Document(str(path))
    props = doc.tables[0]._tbl.tblPr
    if where == "row":
        props = doc.tables[0].rows[0]._tr.get_or_add_trPr()
    elif where == "style":
        style = doc.styles.add_style("SpacedCells", WD_STYLE_TYPE.TABLE)
        props = OxmlElement("w:tblPr")
        style._element.append(props)
        doc.tables[0].style = style
    node = OxmlElement("w:tblCellSpacing")
    node.set(qn("w:w"), width)
    node.set(qn("w:type"), "dxa")
    props.append(node)
    doc.save(str(path))
    result = evaluate(path, truth, sources)
    assert ("UNSUPPORTED_CELL_MARGINS" in result["errors"]) is (width != "0")
    assert result["structure_status"] == ("PASS" if width == "0" else "FAIL")


@pytest.mark.parametrize("tag", ["bookmarkStart", "bookmarkEnd"])
@pytest.mark.parametrize("where", ["pPr", "rPr", "valid"])
def test_bookmark_parent_chain(tmp_path: Path, tag: str, where: str) -> None:
    path, truth, sources = specimen(tmp_path)
    doc: Any = Document(str(path))
    paragraph = doc.paragraphs[0]
    marker = paragraph._p.find(qn("w:" + tag))
    if where == "pPr":
        paragraph._p.get_or_add_pPr().append(marker)
    elif where == "rPr":
        paragraph.runs[0]._r.get_or_add_rPr().append(marker)
    doc.save(str(path))
    result = evaluate(path, truth, sources)
    assert ("INVALID_WORD_STRUCTURE" in result["errors"]) is (where != "valid")
    assert result["structure_status"] == ("PASS" if where == "valid" else "FAIL")
