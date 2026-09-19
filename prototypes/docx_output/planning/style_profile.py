"""Document style evidence and conservative heading levels, independent of source content."""

from __future__ import annotations

import re
import sys
from collections import Counter
from itertools import pairwise
from pathlib import Path
from statistics import median

from ..common import ROOT, Json, read
from ..structure_processors.bridge import json_hash
from ..structure_processors.docvortex import locked


def weighted_sizes(ir: Json, types: set[str]) -> list[Json]:
    """Cluster native measurements within quarter-point tolerance, weighted by real characters."""
    weights: Counter[float] = Counter()
    for page in ir["pages"]:
        for block in page["blocks"]:
            if block["geometry_source"] != "native_pdf" or block["type"] not in types:
                continue
            for run in block["content"].get("runs", []):
                size = run.get("font_size_pt")
                if type(size) in (int, float) and 4 <= size <= 200:
                    weights[float(size)] += sum(not c.isspace() for c in run["text"])
    clusters: list[Json] = []
    for size, weight in sorted(weights.items()):
        if not weight:
            continue
        if clusters and size - clusters[-1]["minimum_pt"] <= 0.25:
            c = clusters[-1]
            c["weighted_sum"] += size * weight
            c["characters"] += weight
            c["maximum_pt"] = size
        else:
            clusters.append(
                {
                    "minimum_pt": size,
                    "maximum_pt": size,
                    "weighted_sum": size * weight,
                    "characters": weight,
                }
            )
    for c in clusters:
        c["size_pt"] = round(c["weighted_sum"] / c["characters"], 2)
    return sorted(clusters, key=lambda c: (-c["characters"], c["size_pt"]))


def font_family(name: str | None, fallback: str, families: set[str]) -> tuple[str, str]:
    """Strip only a PDF subset prefix; never interpret opaque resource IDs as family names."""
    normalized = re.sub(r"^[A-Z]{6}\+", "", name or "")
    by_fold = {f.casefold(): f for f in sorted(families)}
    if normalized.casefold() in by_fold:
        return by_fold[normalized.casefold()], "verified_local_source_family"
    config = read(ROOT / "config/font-mapping.yaml")
    for alias in config["aliases"].get(normalized, []):
        if alias.casefold() in by_fold:
            return by_fold[alias.casefold()], "configured_local_substitution_reflow_risk"
    return fallback, "missing_or_opaque_source_family_reflow_risk"


def heading_candidates(ir: Json) -> list[Json]:
    """Assign only evidenced numbering levels; upstream defaults are never semantic proof."""
    result = []
    defaults = {
        p["source_id"]: p["value"]
        for p in ir["metadata"].get("docvortex_structure", {}).get("proposals", [])
        if p["kind"] == "heading_level"
    }
    previous: tuple[int, ...] | None = None
    previous_page: int | None = None
    complete_start = bool(ir["pages"] and ir["pages"][0]["page_index"] == 0)
    for page in ir["pages"]:
        if previous_page is not None and page["page_index"] != previous_page + 1:
            previous = None
            complete_start = False
        if page.get("page_index") in ir["metadata"].get("document_start_pages", []):
            previous = None
            complete_start = True
        previous_page = page["page_index"]
        blocks = {b["id"]: b for b in page["blocks"]}
        for bid in page["reading_order"]:
            block = blocks[bid]
            if block["type"] != "heading":
                continue
            text = block["content"].get("plain_text", "")
            item: Json = {
                "source_id": bid,
                "text_sha256": json_hash(text),
                "layout_label": "heading",
                "level": None,
                "basis": "unknown",
                "upstream_default_is_prediction": False,
                "upstream_default_level": defaults.get(bid),
            }
            match = re.match(r"^\s*(\d+(?:\.\d+){0,8})(?:\s+|[、．])\S", text)
            if locked(block):
                item["basis"] = "manual_lock_preserved"
            elif not text.strip():
                item["basis"] = "empty_heading"
            elif not complete_start:
                item["basis"] = "partial_import_or_missing_source_pages"
            elif match:
                number = tuple(int(x) for x in match[1].split("."))
                valid_parent = len(number) == 1 or (
                    previous is not None
                    and len(number) <= len(previous) + 1
                    and number[:-1] == previous[: len(number) - 1]
                )
                increasing = previous is None or number > previous
                if valid_parent and increasing:
                    item.update(level=len(number), basis="deterministic_numbering_candidate")
                    previous = number
                else:
                    item["basis"] = "numbering_jump_or_repeat"
            else:
                item["basis"] = "no_reliable_numbering"
            result.append(item)
    return result


def style_profile(ir: Json, output_styles: Json, families: set[str], profile: Json) -> Json:
    """Record source measurement, scan estimates, output policy and local-only font evidence."""
    pages = []
    mappings = []
    evidence = ir["metadata"].get("structure_evidence", {})
    for page in ir["pages"]:
        lines = [
            line for b in page["blocks"] for line in evidence.get(b["id"], {}).get("lines", [])
        ]
        sorted_lines = sorted(lines, key=lambda line: line["bbox"][1])
        gaps = [
            b["bbox"][1] - a["bbox"][1]
            for a, b in pairwise(sorted_lines)
            if b["bbox"][1] > a["bbox"][1]
        ]
        provenance = ir["provenance"].get("pages", {}).get(str(page["page_index"]), {})
        pages.append(
            {
                "page_index": page["page_index"],
                "source_size_pt": [page["width_pt"], page["height_pt"]],
                "size_basis": provenance.get(
                    "size_basis",
                    "source_pdf_points"
                    if Path(ir["source"].get("filename", "")).suffix.lower() == ".pdf"
                    else "virtual_canvas_physical_size_unknown",
                ),
                "mean_characters_per_observed_line": sum(
                    len(line.get("text", "")) for line in lines
                )
                / len(lines)
                if lines
                else None,
                "median_baseline_step_pt": median(gaps) if gaps else None,
                "line_height_is_font_size": False,
            }
        )
        for b in page["blocks"]:
            for i, run in enumerate(b["content"].get("runs", [])):
                resolved, basis = font_family(
                    run.get("font_family"), output_styles["body"]["latin_font"], families
                )
                mappings.append(
                    {
                        "source_id": b["id"],
                        "run_index": i,
                        "source_family": run.get("font_family"),
                        "resolved_latin_family": resolved,
                        "basis": basis,
                    }
                )
    return {
        "schema_version": "style-profile/1",
        "source_state_sha256": json_hash(ir["pages"]),
        "native_size_clusters": weighted_sizes(
            ir, {"paragraph", "question", "option", "text_line"}
        ),
        "roles": output_styles,
        "role_native_clusters": {
            role: weighted_sizes(ir, types)
            for role, types in {
                "heading": {"heading"},
                "caption": {"caption"},
                "list": {"list_item"},
                "option": {"option"},
                "table": {"table"},
            }.items()
        },
        "source_pages": pages,
        "font_mappings": mappings,
        "font_inventory": {
            "host_platform": sys.platform,
            "scope": "supplied_host_local_family_inventory",
            "families": sorted(families),
            "other_operating_systems": "NOT_VERIFIED",
            "font_files_distributed": False,
        },
        "heading_candidates": heading_candidates(ir),
        "overrides": profile,
        "model_calls": 0,
        "external_heading_llm": "DISABLED",
    }
