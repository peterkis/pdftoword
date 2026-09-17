"""Ignorable extension wrappers cannot supply invisible acceptance content."""

import zipfile
from pathlib import Path

import pytest
from lxml import etree
from tests.productization.test_acceptance_harness import specimen

from acceptance.docx_reader import NS
from acceptance.metrics import evaluate


@pytest.mark.parametrize("case", ["paragraph", "run", "text", "process_content", "unused"])
def test_ignorable_wrapper_is_explicitly_unsupported(tmp_path: Path, case: str) -> None:
    path, truth, sources = specimen(tmp_path)
    with zipfile.ZipFile(path) as archive:
        files = {n: archive.read(n) for n in archive.namelist()}
    root = etree.fromstring(files["word/document.xml"])
    replacement = etree.Element(root.tag, nsmap={**root.nsmap, "x": "urn:synthetic-extension"})
    replacement.attrib.update(root.attrib)
    replacement.set("{" + NS["mc"] + "}Ignorable", "x")
    replacement.extend(root)
    root = replacement
    if case == "process_content":
        root.set("{" + NS["mc"] + "}ProcessContent", "x:wrapper")
    if case != "unused":
        expression = {"run": "//w:body/w:p[1]/w:r[1]", "text": "//w:body/w:p[1]/w:r[1]/w:t"}.get(
            case, "//w:body/w:p[1]"
        )
        target = root.xpath(expression, namespaces=NS)[0]
        parent, index = target.getparent(), target.getparent().index(target)
        wrapper = etree.Element("{urn:synthetic-extension}wrapper")
        wrapper.append(target)
        parent.insert(index, wrapper)
    files["word/document.xml"] = etree.tostring(root)
    with zipfile.ZipFile(path, "w") as archive:
        for n, data in files.items():
            archive.writestr(n, data)
    result = evaluate(path, truth, sources)
    assert ("UNSUPPORTED_MARKUP_COMPATIBILITY" in result["errors"]) is (case != "unused")
    assert result["structure_status"] == ("PASS" if case == "unused" else "FAIL")
