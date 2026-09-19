"""Output styles with explicit evidence; never overwrite measured source runs."""

from __future__ import annotations

import shutil
import subprocess
from collections import Counter

from ..common import DemoError, Json


def local_families() -> set[str]:
    """Read installed family names only; do not copy fonts or contact a service."""
    executable = shutil.which("fc-list")
    if not executable:
        return set()
    try:
        output = subprocess.run(
            [executable, "--format=%{family}\n"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        ).stdout
        return {family.strip() for line in output.splitlines() for family in line.split(",")}
    except (OSError, subprocess.SubprocessError):
        return set()


def styles(ir: Json, profile: Json, families: set[str]) -> tuple[Json, list[Json]]:
    """Use the document's measured body size, or a declared inferred scan profile."""
    weights: Counter[float] = Counter()
    for page in ir["pages"]:
        for block in page["blocks"]:
            if block["type"] not in {"paragraph", "question", "option", "text_line"}:
                continue
            for run in block["content"].get("runs", []):
                size = run.get("font_size_pt")
                if (
                    isinstance(size, (int, float))
                    and not isinstance(size, bool)
                    and 0 < size <= 200
                ):
                    weights[round(size, 2)] += len(run["text"])
    body_size = (
        profile["body_size_pt"]
        if "body_size_pt" in profile
        else (weights.most_common(1)[0][0] if weights else 11.0)
    )
    if (
        isinstance(body_size, bool)
        or not isinstance(body_size, (int, float))
        or not 4 <= body_size <= 200
    ):
        raise DemoError("INVALID_FLOW_FONT_SIZE")
    latin = profile.get("latin_font", "Arial")
    east = profile.get("east_asia_font", "Arial Unicode MS")
    if any(not isinstance(family, str) or not family for family in (latin, east)):
        raise DemoError("INVALID_FLOW_FONT_FAMILY")
    issues = [
        {"code": "OUTPUT_FONT_UNVERIFIED", "family": family}
        for family in {latin, east}
        if family not in families
    ]
    basis = (
        "explicit_profile"
        if profile.get("body_size_pt")
        else "native_dominant_size"
        if weights
        else "inferred_scan_profile"
    )
    result = {}
    for role, factor in [("body", 1), ("heading", 1.2), ("caption", 0.95), ("footer", 0.9)]:
        result[role] = {
            "font_size_pt": round(body_size * factor, 2),
            "latin_font": latin,
            "east_asia_font": east,
            "basis": basis if role == "body" else "inferred_role_ratio",
            "alignment": "left",
            "space_before_pt": 0.0,
            "space_after_pt": body_size * 0.25,
            "line_spacing": 1.1,
        }
    return result, issues


def run_styles(
    block: Json, style: Json, families: set[str], *, east_asia_override: bool = False
) -> list[Json]:
    """Preserve run emphasis and size; unresolved source fonts get explicit output mapping."""
    output = []
    for run in block["content"].get("runs", []):
        family = run.get("font_family")
        resolved = family if family in families else style["latin_font"]
        output.append(
            {
                "ascii": resolved,
                "hAnsi": resolved,
                "eastAsia": family
                if family in families
                and not east_asia_override
                and any("\u2e80" <= char <= "\u9fff" for char in run["text"])
                else style["east_asia_font"],
                "font_size_pt": run.get("font_size_pt") or style["font_size_pt"],
                "bold": run.get("bold", False),
                "italic": run.get("italic", False),
                "underline": run.get("underline", False),
                "superscript": run.get("superscript", False),
                "subscript": run.get("subscript", False),
                "color": run.get("color"),
                "source_font": family,
                "font_mapping_basis": "source_family_available"
                if family in families
                else "explicit_output_fallback",
            }
        )
    return output
