"""Immutable native observations for the R2 paragraph bridge; no inferred line boxes."""

from __future__ import annotations

import copy
from itertools import pairwise
from statistics import median

from ..common import Json, union, validate
from ..geometry.candidate import rectangle
from ..structure_processors.bridge import json_hash
from ..structure_processors.docvortex import locked


def native_observations(source: Json) -> Json:
    """Retain original runs and expose only real, unambiguous per-block native lines."""
    validate(source)
    result = copy.deepcopy(source)
    entries = []
    evidence = result["metadata"].setdefault("structure_evidence", {})
    for page in source["pages"]:
        for block in page["blocks"]:
            if block["geometry_source"] != "native_pdf" or block["content"]["kind"] != "text":
                continue
            runs = block["content"].get("runs", [])
            entry: Json = {
                "source_id": block["id"],
                "page_index": page["page_index"],
                "source_block": copy.deepcopy(block),
                "source_sha256": json_hash(block),
                "source_span_ids": [
                    "native-span-"
                    + json_hash([source["source"], page["page_index"], block["id"], i, run])[:24]
                    for i, run in enumerate(runs)
                ],
                "status": "NO_RUN_EVIDENCE",
            }
            entry["prior_structure_evidence"] = copy.deepcopy(evidence.pop(block["id"], {}))
            entries.append(entry)
            if not runs or block.get("rotation", 0) or locked(block):
                entry["status"] = "LOCK_OR_DIRECTION_BOUNDARY" if runs else "NO_RUN_EVIDENCE"
                continue
            rows: list[list[Json]] = []
            try:
                for run in runs:
                    box = rectangle(run["bbox"])
                    if not (
                        0 <= box[0] < box[2] <= page["width_pt"]
                        and 0 <= box[1] < box[3] <= page["height_pt"]
                    ):
                        raise ValueError("OUT_OF_PAGE")
                    center = (box[1] + box[3]) / 2
                    candidates = [
                        row
                        for row in rows
                        if abs(center - (row[0]["bbox"][1] + row[0]["bbox"][3]) / 2)
                        <= max(1, (box[3] - box[1]) * 0.35)
                    ]
                    if len(candidates) > 1:
                        raise ValueError("AMBIGUOUS_BASELINE")
                    if candidates:
                        candidates[0].append(run)
                    else:
                        rows.append([run])
                for row in rows:
                    ordered = sorted(row, key=lambda r: r["bbox"][0])
                    size = median(r.get("font_size_pt") or r["bbox"][3] - r["bbox"][1] for r in row)
                    if any(b["bbox"][0] - a["bbox"][2] > 3 * size for a, b in pairwise(ordered)):
                        raise ValueError("UNPARTITIONED_COLUMN_GAP")
            except (KeyError, ValueError, TypeError):
                entry["status"] = "NATIVE_REGION_REQUIRES_PARTITION"
                continue
            lines = [
                {"bbox": union([r["bbox"] for r in row]), "text": "".join(r["text"] for r in row)}
                for row in rows
            ]
            item = copy.deepcopy(entry["prior_structure_evidence"])
            item.update(
                coordinate_space="pdf_points",
                lines=lines,
                source_span_ids=entry["source_span_ids"],
                _paragraph_boundary=block["type"] != "paragraph",
            )
            evidence[block["id"]] = item
            entry.update(status="OBSERVED_LINES", line_count=len(lines))
    result["metadata"]["native_observation_ledger"] = {
        "schema_version": "native-observations/1",
        "source_ir_sha256": json_hash(source),
        "original_reading_order": {
            str(p["page_index"]): p["reading_order"] for p in source["pages"]
        },
        "entries": entries,
        "presentation_normalizations": [],
    }
    assert result["pages"] == source["pages"] and result["relations"] == source["relations"]
    return result


def build_native_paragraphs(source: Json) -> Json:
    """Build conservative native regions/paragraphs with an exact atomic transition ledger.

    Source blocks are archived verbatim. Only horizontal, single-line observations
    with exact run coverage participate; relation endpoints and opaque groups abstain.
    Public continuation remains a separate subsequent operation.
    """
    import re
    from collections import Counter

    from ..common import DemoError

    if source["metadata"].get("native_paragraphs"):
        raise DemoError("NATIVE_PARAGRAPHS_ALREADY_BUILT")
    result = native_observations(source)
    observations = {
        e["source_id"]: e for e in result["metadata"]["native_observation_ledger"]["entries"]
    }
    evidence = result["metadata"]["structure_evidence"]
    protected = {r[k] for r in source["relations"] for k in ("from", "to")}
    protected.update(source["metadata"].get("inline_parts", {}))
    # Group references have semantics beyond a text box; leave the whole page alone.
    grouped_pages = {
        g["page_index"]
        for kind in ("text_groups", "figure_groups")
        for g in source["metadata"].get(kind, [])
    }
    ledger: Json = {
        "schema_version": "native-paragraphs/1",
        "source_ir_sha256": json_hash(source),
        "entries": [],
        "regions": [],
        "abstentions": [],
        "presentation_normalizations": [],
        "model_calls": 0,
    }
    layout_hints: Json = {}
    marker = re.compile(
        r"^\s*(?:\d+[.．、)）]|\d+(?:[.．]\d+)*[.．、)）]?\s|[a-zA-Z][)）.．、]|[（(]?[一二三四五六七八九十]+[)）、．]|[•●▪])"
    )

    def size(b: Json) -> float:
        return float(
            median(
                r.get("font_size_pt") or r["bbox"][3] - r["bbox"][1] for r in b["content"]["runs"]
            )
        )

    def regions(items: list[Json], scale: float) -> list[list[Json]]:
        """Recursive whitespace cuts; establish x regions before sorting their baselines."""
        if len(items) < 2:
            return [items] if items else []
        for axis, minimum in ((0, 3 * scale), (1, 1.1 * scale)):
            ordered = sorted(items, key=lambda b: b["bbox"][axis])
            edge = ordered[0]["bbox"][axis + 2]
            for i, b in enumerate(ordered[1:], 1):
                if b["bbox"][axis] - edge > minimum:
                    return regions(ordered[:i], scale) + regions(ordered[i:], scale)
                edge = max(edge, b["bbox"][axis + 2])
        return [items]

    for page in result["pages"]:
        originals = {b["id"]: b for b in page["blocks"]}
        eligible, obstacles = [], []
        for b in page["blocks"]:
            entry = observations.get(b["id"], {})
            runs = b["content"].get("runs", [])
            good = (
                page["page_index"] not in grouped_pages
                and b["id"] not in protected
                and not b["children"]
                and not b["relations"]
                and b["type"] in {"paragraph", "heading"}
                and entry.get("status") == "OBSERVED_LINES"
                and entry.get("line_count") == 1
                and "".join(r["text"] for r in runs) == b["content"].get("plain_text")
            )
            if good:
                eligible.append(b)
            else:
                obstacles.append(b)
                if b["id"] in observations:
                    ledger["abstentions"].append(
                        {"source_id": b["id"], "reason": "BOUNDARY_OR_INSUFFICIENT_RUN_EVIDENCE"}
                    )
        if not eligible:
            continue
        scale = float(median(size(b) for b in eligible))
        # Full-width obstacle bands prevent text above/below images or locks joining.
        bands: dict[int, list[Json]] = {}
        for b in eligible:
            if any(b["bbox"][1] < o["bbox"][3] and b["bbox"][3] > o["bbox"][1] for o in obstacles):
                obstacles.append(b)
                ledger["abstentions"].append(
                    {"source_id": b["id"], "reason": "OBSTACLE_VERTICAL_OVERLAP"}
                )
            else:
                band = sum(o["bbox"][3] <= b["bbox"][1] for o in obstacles)
                bands.setdefault(band, []).append(b)
        built: list[Json] = []
        for band in sorted(bands):
            for region in regions(bands[band], scale):
                rid = (
                    "region-"
                    + json_hash([b["id"] for b in sorted(region, key=lambda b: b["id"])])[:20]
                )
                bounds = union([b["bbox"] for b in region])
                ledger["regions"].append(
                    {
                        "id": rid,
                        "page_index": page["page_index"],
                        "bbox": bounds,
                        "source_ids": [b["id"] for b in region],
                        "basis": "recursive_measured_whitespace",
                    }
                )
                rows: list[list[Json]] = []
                for b in sorted(region, key=lambda b: (b["bbox"][1], b["bbox"][0])):
                    center = (b["bbox"][1] + b["bbox"][3]) / 2
                    matches = [
                        row
                        for row in rows
                        if abs(center - (row[0]["bbox"][1] + row[0]["bbox"][3]) / 2)
                        <= 0.35 * min(size(b), size(row[0]))
                    ]
                    if len(matches) == 1:
                        matches[0].append(b)
                    else:
                        rows.append([b])
                lines: list[Json] = []
                for row in rows:
                    row.sort(key=lambda b: b["bbox"][0])
                    # A residual large gutter is ambiguous, never a manufactured line.
                    pieces: list[list[Json]] = [[]]
                    for b in row:
                        if pieces[-1] and b["bbox"][0] - pieces[-1][-1]["bbox"][2] > 3 * scale:
                            pieces.append([])
                        pieces[-1].append(b)
                    for piece in pieces:
                        box = union([b["bbox"] for b in piece])
                        text = "".join(b["content"]["plain_text"] for b in piece)
                        sz = float(median(size(b) for b in piece))
                        heading = (
                            sz > scale * 1.2
                            and len(text) < 100
                            and not text.endswith(("。", ".", ";", "；"))
                        )
                        lines.append(
                            {
                                "blocks": piece,
                                "bbox": box,
                                "text": text,
                                "size": sz,
                                "boundary": bool(marker.match(text)) or heading,
                                "heading": heading,
                                "ambiguous": len(pieces) > 1,
                            }
                        )
                groups: list[list[Json]] = []
                for line in lines:
                    prev = groups[-1][-1] if groups else None
                    join = bool(
                        prev
                        and not line["boundary"]
                        and not prev["heading"]
                        and not prev["ambiguous"]
                        and not line["ambiguous"]
                        and abs(line["size"] - prev["size"]) <= 0.12 * scale
                        and 0 <= line["bbox"][1] - prev["bbox"][3] <= 0.95 * scale
                        and prev["bbox"][2] >= bounds[2] - 2 * scale
                        and (
                            abs(line["bbox"][0] - bounds[0]) <= 0.5 * scale
                            or (
                                groups[-1][0]["boundary"]
                                and 0 <= line["bbox"][0] - bounds[0] <= 3 * scale
                            )
                        )
                        and not prev["text"]
                        .rstrip()
                        .endswith(("。", "！", "？", "；", ";", "!", "?"))
                    )
                    if join:
                        groups[-1].append(line)
                    else:
                        groups.append([line])
                for group in groups:
                    members = [b for line in group for b in line["blocks"]]
                    ids = [b["id"] for b in members]
                    spans = [s for bid in ids for s in observations[bid]["source_span_ids"]]
                    bid = "native-paragraph-" + json_hash(spans)[:24]
                    b = copy.deepcopy(members[0])
                    b.update(
                        id=bid,
                        bbox=union([m["bbox"] for m in members]),
                        type="heading" if group[0]["heading"] else "paragraph",
                    )
                    b["content"]["plain_text"] = "".join(
                        m["content"]["plain_text"] for m in members
                    )
                    b["content"]["runs"] = [
                        copy.deepcopy(r) for m in members for r in m["content"]["runs"]
                    ]
                    b["provenance_refs"] = list(
                        dict.fromkeys(ref for m in members for ref in m["provenance_refs"])
                    )
                    candidate = copy.deepcopy(members[0]["content_candidates"][0])
                    candidate.update(
                        id=bid + "-native",
                        text=b["content"]["plain_text"],
                        selected=True,
                        evidence={"basis": "exact_native_run_assembly", "source_span_ids": spans},
                    )
                    b["content_candidates"] = [candidate]
                    b["selected_candidate_id"] = candidate["id"]
                    if len(members) == 1 and members[0]["type"] == b["type"]:
                        b = copy.deepcopy(members[0])
                        bid = b["id"]
                    built.append(b)
                    for old in ids:
                        evidence.pop(old, None)
                    evidence[bid] = {
                        "coordinate_space": "pdf_points",
                        "lines": [{"bbox": line["bbox"], "text": line["text"]} for line in group],
                        "source_span_ids": spans,
                        "_paragraph_boundary": group[0]["boundary"] or group[0]["ambiguous"],
                    }
                    ledger["entries"].append(
                        {
                            "block_id": bid,
                            "source_ids": ids,
                            "source_span_ids": spans,
                            "region_id": rid,
                            "source_blocks": [copy.deepcopy(originals[i]) for i in ids],
                            "output_sha256": json_hash(b),
                            "line_count": len(group),
                        }
                    )
                    following_left = group[1]["bbox"][0] if len(group) > 1 else group[0]["bbox"][0]
                    layout_hints[bid] = {
                        "body_left_pt": following_left,
                        "first_line_indent_pt": group[0]["bbox"][0] - following_left,
                        "basis": "observed_native_lines",
                        "source_span_ids": spans,
                    }
        # Sort region-major, preserving left-column-before-right within each band.
        # Built order already follows recursive cuts; merge opaque obstacles by vertical band.
        combined = list(built)
        for obstacle in sorted(obstacles, key=lambda b: (b["bbox"][1], b["bbox"][0])):
            pos = next(
                (i for i, b in enumerate(combined) if b["bbox"][1] >= obstacle["bbox"][3]),
                len(combined),
            )
            combined.insert(pos, obstacle)
        page["blocks"] = combined
        page["reading_order"] = [b["id"] for b in combined]
    expected = [b["id"] for p in source["pages"] for b in p["blocks"]]
    replaced = {e["block_id"]: e["source_ids"] for e in ledger["entries"]}
    actual = [
        old
        for p in result["pages"]
        for b in p["blocks"]
        for old in replaced.get(b["id"], [b["id"]])
    ]
    if Counter(expected) != Counter(actual) or len(actual) != len(set(actual)):
        raise DemoError("NATIVE_ATOMIC_COVERAGE_INVALID")
    ledger["coverage"] = {
        "status": "EXACT_ONCE",
        "source_blocks": len(expected),
        "output_blocks": sum(len(p["blocks"]) for p in result["pages"]),
    }
    result["metadata"]["native_paragraphs"] = ledger
    result["metadata"]["native_paragraph_layout"] = layout_hints
    validate(result)
    return result


def verify_native_transition(source: Json, output: Json) -> Json:
    """Independently verify archived candidates, run bytes, atom coverage and relationships."""
    from collections import Counter

    from ..common import DemoError

    ledger = output["metadata"]["native_paragraphs"]
    originals = {b["id"]: b for p in source["pages"] for b in p["blocks"]}
    outputs = {b["id"]: b for p in output["pages"] for b in p["blocks"]}
    seen = []
    if (
        ledger["source_ir_sha256"] != json_hash(source)
        or source["relations"] != output["relations"]
    ):
        raise DemoError("NATIVE_TRANSITION_SOURCE_MISMATCH")
    for e in ledger["entries"]:
        members = [originals[i] for i in e["source_ids"]]
        b = outputs[e["block_id"]]
        if (
            members != e["source_blocks"]
            or json_hash(b) != e["output_sha256"]
            or b["content"]["runs"] != [r for m in members for r in m["content"]["runs"]]
            or b["content"]["plain_text"] != "".join(m["content"]["plain_text"] for m in members)
            or b["bbox"] != union([m["bbox"] for m in members])
            or any(m["page_index"] != b["page_index"] for m in members)
        ):
            raise DemoError("NATIVE_TRANSITION_ATOM_CHANGED")
        seen.extend(e["source_ids"])
    new_ids = {e["block_id"] for e in ledger["entries"]}
    for bid, b in outputs.items():
        if bid not in new_ids:
            if originals.get(bid) != b:
                raise DemoError("NATIVE_TRANSITION_UNDECLARED_CHANGE")
            seen.append(bid)
    if Counter(seen) != Counter(originals.keys()):
        raise DemoError("NATIVE_TRANSITION_COVERAGE_INVALID")
    if source["assets"] != output["assets"]:
        raise DemoError("NATIVE_TRANSITION_ASSET_CHANGED")
    return {
        "status": "VERIFIED",
        "source_blocks": len(seen),
        "output_blocks": len(outputs),
        "model_calls": 0,
        "character_changes": 0,
    }
