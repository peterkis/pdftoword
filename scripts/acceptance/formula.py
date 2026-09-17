"""Independent bounded reference grammar and OMML structural comparison."""

from __future__ import annotations

from typing import Any

SYMBOLS = {
    "alpha": "α",
    "beta": "β",
    "gamma": "γ",
    "leq": "≤",
    "geq": "≥",
    "times": "×",
    "cdot": "·",
    "rightarrow": "→",
    "pm": "±",
}


def reference_tree(text: str) -> Any:
    """Parse literals, braced groups, fractions and scripts; unknown syntax is unsupported."""
    text = "".join(text.split())
    if text.startswith("$$") and text.endswith("$$"):
        text = text[2:-2]
    elif text.startswith("$") and text.endswith("$"):
        text = text[1:-1]
    position = 0

    def atom() -> list[Any]:
        nonlocal position
        if position >= len(text):
            raise ValueError("INCOMPLETE_FORMULA")
        token = text[position]
        position += 1
        if token == "{":
            values = sequence("}")
            if position >= len(text) or text[position] != "}":
                raise ValueError("UNBALANCED_FORMULA")
            position += 1
            return values
        if token == "\\":
            start = position
            while position < len(text) and text[position].isalpha():
                position += 1
            command = text[start:position]
            if command == "frac":
                return [["fraction", atom(), atom()]]
            if command in SYMBOLS:
                return [SYMBOLS[command]]
            raise ValueError("UNSUPPORTED_FORMULA")
        if token in "^_}$":
            raise ValueError("UNEXPECTED_FORMULA_TOKEN")
        return [token]

    def sequence(stop: str = "") -> list[Any]:
        nonlocal position
        values: list[Any] = []
        while position < len(text) and (not stop or text[position] != stop):
            base = atom()
            scripts: dict[str, Any] = {}
            while position < len(text) and text[position] in "^_":
                key = text[position]
                position += 1
                if key in scripts:
                    raise ValueError("DUPLICATE_SCRIPT")
                scripts[key] = atom()
            if scripts:
                values.append(["script", base, scripts.get("_"), scripts.get("^")])
            else:
                values.extend(base)
        return values

    try:
        result = sequence()
        return result if result and position == len(text) else None
    except (ValueError, RecursionError):
        return None


def output_tree(tree: Any) -> Any:
    """Interpret actual OMML structure without calling the converter's formula parser."""
    name, text, children = tree
    if name == "t":
        return list("".join(text.split()))
    if name in {"oMath", "r", "e", "num", "den", "sup", "sub"}:
        parts = [output_tree(c) for c in children]
        if any(p is None for p in parts):
            return None
        return [v for p in parts for v in p]
    required = {
        "f": ["num", "den"],
        "sSup": ["e", "sup"],
        "sSub": ["e", "sub"],
        "sSubSup": ["e", "sub", "sup"],
    }
    if name not in required or [c[0] for c in children] != required[name]:
        return None
    fields = {c[0]: output_tree(c) for c in children}
    if any(v is None for v in fields.values()):
        return None
    if name == "f":
        return [["fraction", fields["num"], fields["den"]]]
    return [["script", fields["e"], fields.get("sub"), fields.get("sup")]]
