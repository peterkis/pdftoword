"""Frozen Monkey chat-wire parser; no execution, content recovery, or network."""

from __future__ import annotations

import ast
import io
import json
import tokenize
from typing import Any

from ..common import Json
from .candidate import MAX_REGIONS, TransformChain, append_unique, record, result

MAX_BYTES = 2_000_000
MAX_DEPTH = 16
MAX_NODES = 100_000


def parse(body: Json) -> list[Any]:
    """Parse JSON or legal Python literals with limits before literal evaluation."""
    try:
        choices = body["choices"]
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("INVALID_CHAT_WIRE")
        choice = choices[0]
        if choice["finish_reason"] != "stop":
            raise ValueError("INCOMPLETE_FINISH_REASON")
        content = choice["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("INVALID_CHAT_WIRE")
        if len(content) > MAX_BYTES or len(content.encode("utf-8")) > MAX_BYTES:
            raise ValueError("RESPONSE_TOO_LARGE")
        # Tokenize before parsing to bound nesting without counting brackets in strings.
        depth = 0
        for count, token in enumerate(tokenize.generate_tokens(io.StringIO(content).readline), 1):
            if token.type == tokenize.OP:
                if token.string in {"[", "{", "("}:
                    depth += 1
                elif token.string in {"]", "}", ")"}:
                    depth -= 1
            if depth > MAX_DEPTH or count > MAX_NODES:
                raise ValueError("RESPONSE_COMPLEXITY_LIMIT")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = ast.literal_eval(content.strip())
        if not isinstance(parsed, list) or any(not isinstance(row, dict) for row in parsed):
            raise ValueError("INVALID_REGION_ARRAY")
        if len(parsed) > MAX_REGIONS:
            raise ValueError("REGION_COUNT_LIMIT")
        return parsed
    except (
        KeyError,
        TypeError,
        AttributeError,
        SyntaxError,
        tokenize.TokenError,
        RecursionError,
        MemoryError,
        UnicodeError,
    ):
        raise ValueError("INVALID_CHAT_WIRE") from None


def adapt(body: Json, page_index: int, chain: TransformChain, evidence: Json) -> Json:
    """Reject only this provider or region, retaining failures and source indices."""
    output = result()
    try:
        rows = parse(body)
    except ValueError as exc:
        # Only parser-owned codes are surfaced, never literal_eval's source diagnostics.
        code = str(exc)
        if code not in {
            "INVALID_CHAT_WIRE",
            "INCOMPLETE_FINISH_REASON",
            "RESPONSE_TOO_LARGE",
            "RESPONSE_COMPLEXITY_LIMIT",
            "INVALID_REGION_ARRAY",
            "REGION_COUNT_LIMIT",
        }:
            code = "INVALID_LITERAL"
        output["rejections"].append({"provider": "monkey", "index": None, "reason": code})
        return output
    for index, row in enumerate(rows):
        try:
            candidate = record(
                "monkey",
                page_index,
                index,
                row.get("label"),
                "region",
                "semantic_region",
                row.get("bbox"),
                "normalized_1000",
                chain,
                {"model_fingerprint": None, "prompt_fingerprint": None, **evidence},
            )
            append_unique(output, candidate)
        except (ValueError, TypeError, KeyError, IndexError):
            output["rejections"].append(
                {"provider": "monkey", "index": index, "reason": "INVALID_OR_DUPLICATE_GEOMETRY"}
            )
    return output
