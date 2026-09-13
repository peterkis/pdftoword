"""Bounded LaTeX-to-OMML conversion; unsupported syntax fails closed."""

from __future__ import annotations

import re
from typing import Any

from lxml import etree

from .common import DemoError

M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
SYMBOLS = {
    "neq": "≠",
    "leq": "≤",
    "geq": "≥",
    "times": "×",
    "cdot": "·",
    "pm": "±",
    "alpha": "α",
    "beta": "β",
    "theta": "θ",
    "pi": "π",
}


def node(name: str, *children: Any) -> Any:
    """Construct only Math namespace elements, never arbitrary model XML."""
    el = etree.Element("{" + M + "}" + name)
    for child in children:
        el.append(child)
    return el


def run(text: str) -> Any:
    """Make an editable math run."""
    value = node("t")
    value.text = text
    return node("r", value)


class Parser:
    """Parse fractions, roots, scripts, literal operators and a small symbol set."""

    def __init__(self, latex: str) -> None:
        self.tokens = re.findall(r"\\[A-Za-z]+|\\.|[^\s]", latex)
        self.index = 0
        if len(self.tokens) > 1024:
            raise DemoError("FORMULA_TOO_COMPLEX")

    def group(self, depth: int) -> list[Any]:
        """Read a braced group or one LaTeX atom."""
        if depth > 32 or self.index >= len(self.tokens):
            raise DemoError("UNSUPPORTED_FORMULA")
        if self.tokens[self.index] != "{":
            return [self.atom(depth + 1)]
        self.index += 1
        result = self.sequence(depth + 1)
        if self.index >= len(self.tokens) or self.tokens[self.index] != "}":
            raise DemoError("UNBALANCED_FORMULA")
        self.index += 1
        if not result:
            raise DemoError("EMPTY_FORMULA_GROUP")
        return result

    def atom(self, depth: int) -> Any:
        """Parse a single supported math atom."""
        if depth > 32 or self.index >= len(self.tokens):
            raise DemoError("UNSUPPORTED_FORMULA")
        token = self.tokens[self.index]
        self.index += 1
        if token == r"\frac":
            numerator = self.group(depth + 1)
            denominator = self.group(depth + 1)
            return node("f", node("num", *numerator), node("den", *denominator))
        if token == r"\sqrt":
            if self.index < len(self.tokens) and self.tokens[self.index] == "[":
                raise DemoError("UNSUPPORTED_INDEXED_ROOT")
            properties = node("radPr")
            hide = node("degHide")
            hide.set("{" + M + "}val", "1")
            properties.append(hide)
            return node("rad", properties, node("deg"), node("e", *self.group(depth + 1)))
        if token.startswith("\\"):
            if token[1:] not in SYMBOLS:
                raise DemoError("UNSUPPORTED_FORMULA_COMMAND")
            return run(SYMBOLS[token[1:]])
        if token in "{}^_$&#" or not (token.isalnum() or token in "+-=<>(),.[]|/:!"):
            raise DemoError("UNSUPPORTED_FORMULA_TOKEN")
        return run(token)

    def sequence(self, depth: int = 0) -> list[Any]:
        """Parse scripts without flattening fractions or changing operators."""
        output = []
        while self.index < len(self.tokens) and self.tokens[self.index] != "}":
            if self.tokens[self.index] == "{":
                base = self.group(depth + 1)
            else:
                base = [self.atom(depth + 1)]
            scripts = {}
            while self.index < len(self.tokens) and self.tokens[self.index] in {"^", "_"}:
                operator = self.tokens[self.index]
                self.index += 1
                if operator in scripts:
                    raise DemoError("DUPLICATE_FORMULA_SCRIPT")
                scripts[operator] = self.group(depth + 1)
            if "^" in scripts and "_" in scripts:
                output.append(
                    node(
                        "sSubSup",
                        node("e", *base),
                        node("sub", *scripts["_"]),
                        node("sup", *scripts["^"]),
                    )
                )
            elif scripts:
                operator = next(iter(scripts))
                output.append(
                    node(
                        "sSup" if operator == "^" else "sSub",
                        node("e", *base),
                        node("sup" if operator == "^" else "sub", *scripts[operator]),
                    )
                )
            else:
                output.extend(base)
        return output


def to_omml(latex: str) -> str:
    """Convert a supported expression to editable OMML or raise a safe diagnostic."""
    parser = Parser(latex)
    result = parser.sequence()
    if parser.index != len(parser.tokens) or not result:
        raise DemoError("UNBALANCED_FORMULA")
    return str(etree.tostring(node("oMath", *result), encoding="unicode"))


def unrendered_math(text: str) -> bool:
    """Recognize remaining math delimiters/commands without rejecting ordinary escapes."""
    noncurrency = re.sub(r"(?<![\w$])(?:US|HK|CA|AU|NZ|SG|NT|A|C|S)?\$\d+(?:[.,]\d+)*", "", text)
    if any(marker in text for marker in (r"\(", r"\)", r"\[", r"\]")):
        return True
    if "$" in noncurrency:
        return True
    commands = set(SYMBOLS) | {
        "frac",
        "dfrac",
        "tfrac",
        "sqrt",
        "sum",
        "prod",
        "int",
        "lim",
        "sin",
        "cos",
        "tan",
        "log",
        "ln",
        "left",
        "right",
        "begin",
        "end",
        "mathrm",
        "mathbf",
        "text",
        "overline",
        "underline",
        "vec",
        "hat",
        "infty",
        "le",
        "ge",
        "ne",
    }
    for match in re.finditer(r"\\([A-Za-z]+)", text):
        if match[1] in commands or text[match.end() :].lstrip().startswith("{"):
            return True
    return False
