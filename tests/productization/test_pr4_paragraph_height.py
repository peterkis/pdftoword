"""Paragraph line boxes must not clip or overlap acceptance glyphs."""

from pathlib import Path
from typing import Any

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from tests.productization.test_acceptance_harness import specimen

from acceptance.metrics import evaluate


@pytest.mark.parametrize("where", ["direct", "math", "style", "default"])
@pytest.mark.parametrize(
    "rule,line,invalid",
    [("exact", "1", True), ("auto", "1", True), ("auto", "240", False), ("atLeast", "1", False)],
)
def test_paragraph_line_height(
    tmp_path: Path, where: str, rule: str, line: str, invalid: bool
) -> None:
    path, truth, sources = specimen(tmp_path)
    doc: Any = Document(str(path))
    props = doc.paragraphs[2 if where == "math" else 0]._p.get_or_add_pPr()
    if where == "style":
        props = doc.styles["Normal"]._element.get_or_add_pPr()
    elif where == "default":
        props = doc.styles._element.xpath("./w:docDefaults/w:pPrDefault/w:pPr")[0]
    for old in props.findall(qn("w:spacing")):
        props.remove(old)
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:lineRule"), rule)
    spacing.set(qn("w:line"), line)
    props.append(spacing)
    doc.save(str(path))
    result = evaluate(path, truth, sources)
    assert ("UNSUPPORTED_LINE_HEIGHT" in result["errors"]) is invalid
    assert result["structure_status"] == ("FAIL" if invalid else "PASS")
