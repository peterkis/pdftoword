"""Explicit bidi directions require a display-order evaluator we do not yet provide."""

from pathlib import Path
from typing import Any

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from tests.productization.test_acceptance_harness import specimen

from acceptance.metrics import evaluate


@pytest.mark.parametrize("tag", ["bidi", "rtl"])
@pytest.mark.parametrize("where", ["direct", "math", "style", "default"])
@pytest.mark.parametrize("enabled", [True, False])
def test_explicit_bidi_directions(tmp_path: Path, tag: str, where: str, enabled: bool) -> None:
    path, truth, sources = specimen(tmp_path)
    doc: Any = Document(str(path))
    paragraph = doc.paragraphs[2 if where == "math" else 0]
    if tag == "bidi":
        props = paragraph._p.get_or_add_pPr()
    elif where == "math":
        props = OxmlElement("w:rPr")
        paragraph._p.xpath(".//m:r")[0].insert(0, props)
    else:
        props = paragraph.runs[0]._r.get_or_add_rPr()
    if where == "style":
        props = (
            doc.styles["Normal"]._element.get_or_add_pPr()
            if tag == "bidi"
            else doc.styles["Normal"]._element.get_or_add_rPr()
        )
    elif where == "default":
        kind = "pPr" if tag == "bidi" else "rPr"
        props = doc.styles._element.xpath("./w:docDefaults/w:" + kind + "Default/w:" + kind)[0]
    node = OxmlElement("w:" + tag)
    node.set(qn("w:val"), "true" if enabled else "false")
    props.append(node)
    doc.save(str(path))
    result = evaluate(path, truth, sources)
    assert ("UNSUPPORTED_BIDI_OVERRIDE" in result["errors"]) is enabled
    assert result["structure_status"] == ("FAIL" if enabled else "PASS")
