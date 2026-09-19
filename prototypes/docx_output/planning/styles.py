"""Output styles with explicit evidence; never overwrite measured source runs."""

from __future__ import annotations

import shutil
import subprocess

from ..common import ROOT, DemoError, Json, read
from .style_profile import font_family, weighted_sizes


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
    clusters = weighted_sizes(ir, {"paragraph", "question", "option", "text_line"})
    weights = bool(clusters)
    body_size = (
        profile["body_size_pt"]
        if "body_size_pt" in profile
        else (clusters[0]["size_pt"] if weights else 11.0)
    )
    if (
        isinstance(body_size, bool)
        or not isinstance(body_size, (int, float))
        or not 4 <= body_size <= 200
    ):
        raise DemoError("INVALID_FLOW_FONT_SIZE")
    mapping = read(ROOT / "config/font-mapping.yaml")
    latin = profile.get("latin_font", next((f for f in mapping["latin"] if f in families), "Arial"))
    east = profile.get(
        "east_asia_font",
        next((f for f in mapping["east_asia"] if f in families), "Arial Unicode MS"),
    )
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
        else "unmeasured_native_body_default"
        if any(b["geometry_source"] == "native_pdf" for page in ir["pages"] for b in page["blocks"])
        else "inferred_scan_profile"
    )
    result = {}
    for role, factor in [
        ("body", 1),
        ("heading", 1.2),
        ("caption", 0.95),
        ("footer", 0.9),
        ("list", 1),
        ("option", 1),
        ("table", 1),
    ]:
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
    block: Json,
    style: Json,
    families: set[str],
    *,
    east_asia_override: bool = False,
    size_scale: float = 1.0,
    editable_styles: bool = False,
) -> list[Json]:
    """Preserve run emphasis and size; unresolved source fonts get explicit output mapping."""
    output = []
    for run in block["content"].get("runs", []):
        family = run.get("font_family")
        resolved, mapping_basis = font_family(family, style["latin_font"], families)
        east_resolved = style["east_asia_font"]
        if not east_asia_override and any("\u2e80" <= c <= "\u9fff" for c in run["text"]):
            east_resolved, _ = font_family(family, style["east_asia_font"], families)
        output_size = (run.get("font_size_pt") or style["font_size_pt"]) * size_scale
        output.append(
            {
                "ascii": resolved,
                "hAnsi": resolved,
                "eastAsia": east_resolved,
                "font_size_pt": output_size,
                "inherit_fonts": resolved == style["latin_font"]
                and east_resolved == style["east_asia_font"],
                "inherit_base": editable_styles
                and abs(output_size - style["font_size_pt"]) <= 0.25
                and not any(
                    run.get(k)
                    for k in ("bold", "italic", "superscript", "subscript", "underline", "color")
                ),
                "bold": run.get("bold", False),
                "italic": run.get("italic", False),
                "underline": run.get("underline", False),
                "superscript": run.get("superscript", False),
                "subscript": run.get("subscript", False),
                "color": run.get("color"),
                "source_font": family,
                "font_mapping_basis": mapping_basis,
            }
        )
    return output
