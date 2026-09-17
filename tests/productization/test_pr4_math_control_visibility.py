"""Fraction/control glyph styling must not be discarded before visibility checks."""

from pathlib import Path
from typing import Any

import pytest
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from tests.productization.test_acceptance_harness import specimen

from acceptance.metrics import evaluate


@pytest.mark.parametrize("case", ["white", "hidden", "tiny", "position", "style", "visible"])
def test_math_control_properties(tmp_path: Path, case: str) -> None:
    path, truth, sources = specimen(tmp_path)
    doc: Any = Document(str(path))
    paragraph = doc.paragraphs[2]._p
    paragraph.remove(paragraph.xpath(".//m:oMath")[0])
    math, fraction, props = OxmlElement("m:oMath"), OxmlElement("m:f"), OxmlElement("m:fPr")
    control, runs = OxmlElement("m:ctrlPr"), OxmlElement("w:rPr")
    tag, value = {
        "white": ("color", "FFFFFF"),
        "hidden": ("vanish", "true"),
        "tiny": ("sz", "1"),
        "position": ("position", "31680"),
        "style": ("rStyle", "HiddenControl"),
        "visible": ("vanish", "false"),
    }[case]
    if case == "style":
        style = doc.styles.add_style("HiddenControl", WD_STYLE_TYPE.CHARACTER)
        style.font.hidden = True
    node = OxmlElement("w:" + tag)
    node.set(qn("w:val"), value)
    runs.append(node)
    control.append(runs)
    props.append(control)
    fraction.append(props)
    for part, value in [("num", "1"), ("den", "2")]:
        container, run, text = OxmlElement("m:" + part), OxmlElement("m:r"), OxmlElement("m:t")
        text.text = value
        run.append(text)
        container.append(run)
        fraction.append(container)
    math.append(fraction)
    paragraph.append(math)
    next(u for u in truth["units"] if u["unit_id"] == "f")["reference"]["text"] = r"\frac{1}{2}"
    doc.save(str(path))
    result = evaluate(path, truth, sources)
    assert result["structure_status"] == ("PASS" if case == "visible" else "FAIL")
    if case != "visible":
        assert any(
            c in result["errors"]
            for c in {
                "HIDDEN_CONTENT",
                "UNSUPPORTED_VISIBILITY_STYLE",
                "UNSUPPORTED_FONT_SCALE",
                "UNSUPPORTED_TEXT_POSITION",
            }
        )
