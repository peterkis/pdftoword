"""Conservative source-to-OOXML checks; unsupported structures fail closed."""

from __future__ import annotations

from typing import Any

from docx.oxml.ns import qn
from docx.table import Table
from lxml import etree, html

from ..common import DemoError
from ..formula import to_omml
from ..structure_processors.bridge import table_text


def verify_table(element: Any, markup: str, parent: Any) -> None:
    """Compare cell text and exact rectangular row/column ownership, including merges."""
    root = html.fragment_fromstring(
        markup, create_parent="div", parser=html.HTMLParser(no_network=True)
    )
    tables = root.findall(".//table")
    if len(tables) != 1 or element.tag != qn("w:tbl"):
        raise DemoError("DOCVORTEX_TABLE_TOPOLOGY_UNVERIFIED")
    rows = tables[0].xpath("./tr|./thead/tr|./tbody/tr|./tfoot/tr")
    occupied: dict[tuple[int, int], tuple[int, int, int, int, str]] = {}
    expected = []
    try:
        for row_index, row in enumerate(rows):
            column = 0
            for cell in row.xpath("./td|./th"):
                while (row_index, column) in occupied:
                    column += 1
                rs, cs = int(cell.get("rowspan", "1")), int(cell.get("colspan", "1"))
                if not (1 <= rs <= len(rows) - row_index and 1 <= cs <= 1000):
                    raise ValueError
                record = (
                    row_index,
                    column,
                    rs,
                    cs,
                    table_text(etree.tostring(cell, encoding="unicode", method="html")),
                )
                expected.append(record)
                for r in range(row_index, row_index + rs):
                    for c in range(column, column + cs):
                        if (r, c) in occupied:
                            raise ValueError
                        occupied[r, c] = record
                column += cs
        width = max((c for _, c in occupied), default=-1) + 1
        if not width or len(occupied) != len(rows) * width:
            raise ValueError
        table = Table(element, parent)
        if len(table.rows) != len(rows) or len(table.columns) != width:
            raise ValueError
        groups: dict[Any, list[tuple[int, int]]] = {}
        for r, row in enumerate(table.rows):
            if row.grid_cols_before or row.grid_cols_after or len(row.cells) != width:
                raise ValueError
            for c, cell in enumerate(row.cells):
                groups.setdefault(cell._tc, []).append((r, c))
        actual = []
        for tc, positions in groups.items():
            r, c = min(positions)
            rs = max(p[0] for p in positions) - r + 1
            cs = max(p[1] for p in positions) - c + 1
            if len(positions) != rs * cs or tc.xpath(".//w:tbl|.//w:drawing|.//m:oMath"):
                raise ValueError
            actual.append((r, c, rs, cs, table.cell(r, c).text))
        if sorted(expected) != sorted(actual):
            raise ValueError
    except (ValueError, IndexError, KeyError):
        raise DemoError("DOCVORTEX_TABLE_TOPOLOGY_CHANGED") from None


def verify_formula(element: Any, latex: str) -> None:
    """Compare a bounded math tree with the existing source parser; reject unknown syntax."""

    def tokens(node: Any) -> list[Any]:
        name = etree.QName(node).localname
        if node.tag == qn("m:rPr"):
            if any(
                child.tag != qn("m:sty") or child.get(qn("m:val")) not in {"i", "p"}
                for child in node
            ):
                raise DemoError("DOCVORTEX_FORMULA_UNVERIFIED")
            return []
        if node.tag == qn("m:t"):
            return list(node.text or "")
        if name == "box" and node.tag == qn("m:box"):
            if len(node) != 1 or node[0].tag != qn("m:e"):
                raise DemoError("DOCVORTEX_FORMULA_UNVERIFIED")
            return [item for child in node[0] for item in tokens(child)]
        if (
            name
            not in {"oMath", "r", "e", "f", "num", "den", "sSub", "sSup", "sSubSup", "sub", "sup"}
            or node.tag != qn("m:" + name)
            or node.attrib
        ):
            raise DemoError("DOCVORTEX_FORMULA_UNVERIFIED")
        children = [item for child in node for item in tokens(child)]
        return children if name in {"oMath", "r"} else [(name, tuple(children))]

    try:
        reference = etree.fromstring(to_omml(latex).encode())
        if tokens(element) != tokens(reference):
            raise DemoError("DOCVORTEX_FORMULA_CHANGED")
    except DemoError as exc:
        raise DemoError("DOCVORTEX_FORMULA_UNVERIFIED:" + str(exc)) from None


def verify_inline_order(element: Any, spans: list[Any]) -> None:
    """Validate one interleaved stream of literal characters and source math nodes."""
    from ..structure_processors.bridge import inline_text

    expected: list[tuple[str, Any]] = []
    for span in spans:
        if span.get("type") == "equation_inline":
            expected.append(("math", inline_text(span.get("content"))))
        else:
            expected.extend(("text", char) for char in inline_text(span.get("content")))
    actual: list[tuple[str, Any]] = []

    def walk(node: Any) -> None:
        if node.tag == qn("m:oMath"):
            actual.append(("math", node))
        elif node.tag == qn("w:t"):
            actual.extend(("text", char) for char in node.text or "")
        elif node.tag in {qn("w:br"), qn("w:cr"), qn("w:tab")}:
            actual.append(("text", "\t" if node.tag == qn("w:tab") else "\n"))
        else:
            for child in node:
                walk(child)

    walk(element)
    if len(expected) != len(actual):
        raise DemoError("DOCVORTEX_INLINE_ORDER_CHANGED")
    for (kind, source), (actual_kind, output) in zip(expected, actual, strict=True):
        if kind != actual_kind or (kind == "text" and source != output):
            raise DemoError("DOCVORTEX_INLINE_ORDER_CHANGED")
        if kind == "math":
            verify_formula(output, source)
