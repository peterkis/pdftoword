"""Bounded horizontal bands and measured column containers, shared by native and scan IR."""

from __future__ import annotations

import copy
from itertools import pairwise

from ..common import DemoError, Json, issue, union, validate
from ..geometry.candidate import rectangle
from ..structure_processors.bridge import json_hash
from ..structure_processors.docvortex import locked
from .reading_order import resolve_order


def page_bands(page: Json) -> list[Json]:
    """Separate true spanning regions before finding gutters inside each horizontal band."""
    blocks = page["blocks"]
    if not blocks:
        return []
    width = max(b["bbox"][2] for b in blocks) - min(b["bbox"][0] for b in blocks)

    def overlap(a: Json, b: Json) -> bool:
        return bool(min(a["bbox"][3], b["bbox"][3]) > max(a["bbox"][1], b["bbox"][1]))

    spans = []
    for b in blocks:
        box = rectangle(b["bbox"])
        if not (
            0 <= box[0] < box[2] <= page["width_pt"] and 0 <= box[1] < box[3] <= page["height_pt"]
        ):
            raise DemoError("COLUMN_BOX_OUT_OF_PAGE")
        if b.get("rotation") or (
            b["geometry_source"]
            not in {
                "native_pdf",
                "pp_structure",
                "monkeyocrv2",
            }
            and not (
                b["content"]["kind"] == "image"
                and b["geometry_source"] in {"pdf_image", "pdf_vector_render"}
            )
        ):
            raise DemoError("COLUMN_GEOMETRY_OR_DIRECTION_UNPROVEN")
        if (
            box[2] - box[0] >= 0.7 * width
            or b["type"] in {"footer", "page_number"}
            or (
                b["type"] == "heading"
                and not any(o["id"] != b["id"] and overlap(b, o) for o in blocks)
            )
        ):
            spans.append(b)
    # Expand a spanning interval over intersecting content; ambiguous overlap stays local.
    clusters: list[list[Json]] = []
    assigned: set[str] = set()
    for span in sorted(spans, key=lambda b: b["bbox"][1]):
        if span["id"] in assigned:
            continue
        cluster = [span]
        changed = True
        while changed:
            bounds = union([b["bbox"] for b in cluster])
            changed = False
            for b in blocks:
                if (
                    b["id"] not in {x["id"] for x in cluster}
                    and b["id"] not in assigned
                    and min(bounds[3], b["bbox"][3]) > max(bounds[1], b["bbox"][1])
                ):
                    cluster.append(b)
                    changed = True
        assigned.update(b["id"] for b in cluster)
        clusters.append(cluster)
    remaining = [b for b in blocks if b["id"] not in assigned]
    bands = []
    for cluster in clusters:
        top = min(b["bbox"][1] for b in cluster)
        preceding = [b for b in remaining if b["bbox"][3] <= top]
        if preceding:
            bands.append({"blocks": preceding, "spanning": False})
        remaining = [b for b in remaining if b not in preceding]
        bands.append({"blocks": cluster, "spanning": True})
    if remaining:
        bands.append({"blocks": remaining, "spanning": False})
    if not bands:
        bands = [{"blocks": blocks, "spanning": False}]
    return bands


def column_containers(blocks: list[Json], page_width: float) -> tuple[list[list[Json]], str | None]:
    """Prove disjoint x containers with simultaneous vertical coverage, otherwise abstain."""
    if any(b["type"] == "table" for b in blocks):
        return [blocks], "COLUMN_TABLE_SCOPE_UNSUPPORTED"
    groups: list[list[Json]] = []
    for b in sorted(blocks, key=lambda b: b["bbox"][0]):
        if groups and b["bbox"][0] <= max(o["bbox"][2] for o in groups[-1]) + 2:
            groups[-1].append(b)
        else:
            groups.append([b])
    if len(groups) == 1:
        return groups, None
    if not 2 <= len(groups) <= 4:
        return [blocks], "COLUMN_COUNT_UNSUPPORTED"
    bounds = [union([b["bbox"] for b in g]) for g in groups]
    for left_box, right_box in pairwise(bounds):
        if right_box[0] - left_box[2] < max(8, page_width * 0.015) or min(
            left_box[3], right_box[3]
        ) - max(left_box[1], right_box[1]) < 0.3 * min(
            left_box[3] - left_box[1], right_box[3] - right_box[1]
        ):
            return [blocks], "COLUMN_GUTTER_OR_VERTICAL_SUPPORT_MISSING"
    for group in groups:
        ordered = sorted(group, key=lambda b: (b["bbox"][1], b["bbox"][0]))
        if any(a["bbox"][3] > b["bbox"][1] + 1 for a, b in pairwise(ordered)):
            return [blocks], "COLUMN_INTERNAL_ORDER_AMBIGUOUS"
    return groups, None


def select_columns(source: Json) -> Json:
    """Select order before shared processing, retaining original blocks and provenance verbatim."""
    validate(source)
    result = copy.deepcopy(source)
    reports: Json = {}
    for page in result["pages"]:
        original = list(page["reading_order"])
        rank = {bid: i for i, bid in enumerate(original)}
        report: Json = {
            "schema_version": "band-columns/1",
            "source_page_sha256": json_hash(page),
            "source_order": original,
            "source_blocks_sha256": json_hash(page["blocks"]),
            "status": "SINGLE_COLUMN",
            "bands": [],
            "edges": [],
            "engine_confidence": None,
            "provider_constraints": [],
            "provider_order_status": "MISSING_OR_UNVERIFIED",
        }
        reports[str(page["page_index"])] = report
        try:
            if any(locked(b) for b in page["blocks"]):
                raise DemoError("COLUMN_MANUAL_LOCK")
            if any(
                g["page_index"] == page["page_index"]
                for kind in ("text_groups", "figure_groups")
                for g in source["metadata"].get(kind, [])
            ):
                raise DemoError("EXISTING_LOCAL_GROUP_RETAINED")
            selected = []
            for bi, band in enumerate(page_bands(page)):
                blocks = band["blocks"]
                columns, reason = (
                    ([blocks], None)
                    if band["spanning"]
                    else column_containers(blocks, page["width_pt"])
                )
                ambiguous_span = band["spanning"] and len(blocks) > 1
                if ambiguous_span:
                    reason = "SPANNING_REGION_OVERLAP"
                bid = f"p{page['page_index']}-band{bi}"
                cols = []
                for ci, group in enumerate(columns):
                    ordered = sorted(
                        group,
                        key=lambda b: rank[b["id"]] if reason else (b["bbox"][1], b["bbox"][0]),
                    )
                    ids = [b["id"] for b in ordered]
                    cols.append(
                        {
                            "id": f"{bid}-column{ci}",
                            "source_ids": ids,
                            "bbox": union([b["bbox"] for b in group]),
                        }
                    )
                    selected.extend(ids)
                    for a, b in pairwise(ids):
                        report["edges"].append(
                            {
                                "from": a,
                                "to": b,
                                "basis": "retained_local_order" if reason else "within_column_y",
                            }
                        )
                for left, right in pairwise(cols):
                    report["edges"].append(
                        {
                            "from": left["source_ids"][-1],
                            "to": right["source_ids"][0],
                            "basis": "left_column_before_right",
                        }
                    )
                report["bands"].append(
                    {
                        "id": bid,
                        "columns": cols,
                        "status": "ABSTAIN" if reason else "PROVEN",
                        "reason": reason,
                        "spanning": band["spanning"],
                    }
                )
            for a, b in pairwise(report["bands"]):
                report["edges"].append(
                    {
                        "from": a["columns"][-1]["source_ids"][-1],
                        "to": b["columns"][0]["source_ids"][0],
                        "basis": "band_before_band",
                    }
                )
            by_id = {b["id"]: b for b in page["blocks"]}
            for edge in source["relations"]:
                if (
                    edge["from"] in by_id
                    and edge["to"] in by_id
                    and edge["type"] in {"precedes", "follows"}
                ):
                    a, b = (
                        (edge["from"], edge["to"])
                        if edge["type"] == "precedes"
                        else (edge["to"], edge["from"])
                    )
                    report["edges"].append(
                        {
                            "from": a,
                            "to": b,
                            "basis": "explicit_relation",
                            "relation_id": edge["id"],
                        }
                    )
                if edge["type"] == "caption_of" and edge["from"] in by_id and edge["to"] in by_id:
                    cap, fig = by_id[edge["from"]], by_id[edge["to"]]
                    if cap["bbox"][3] <= fig["bbox"][1]:
                        a, b = cap["id"], fig["id"]
                    elif fig["bbox"][3] <= cap["bbox"][1]:
                        a, b = fig["id"], cap["id"]
                    else:
                        continue
                    report["edges"].append(
                        {
                            "from": a,
                            "to": b,
                            "basis": "caption_relation_and_vertical_evidence",
                            "relation_id": edge["id"],
                        }
                    )
            # Only explicitly source-bound sequences are constraints; raw array indices are not.
            for evidence in (
                source["metadata"]
                .get("reading_order_evidence", {})
                .get(str(page["page_index"]), [])
            ):
                valid = (
                    evidence.get("source_page_sha256") == report["source_page_sha256"]
                    and evidence.get("provider") in {"pp_structure", "monkeyocrv2"}
                    and evidence.get("source_content_sha256")
                    == {
                        bid: json_hash(by_id[bid]["content"])
                        for bid in evidence.get("source_ids", [])
                        if bid in by_id
                    }
                )
                ids = evidence.get("source_ids", [])
                if (
                    not valid
                    or len(ids) < 2
                    or len(ids) != len(set(ids))
                    or not set(ids) <= set(original)
                ):
                    report["provider_constraints"].append(
                        {"status": "REJECTED", "reason": "ORDER_BINDING_MISSING_OR_STALE"}
                    )
                    continue
                report["provider_order_status"] = "BOUND_CONSTRAINTS"
                report["provider_constraints"].append(
                    {"status": "BOUND", "evidence_sha256": json_hash(evidence)}
                )
                for a, b in pairwise(ids):
                    report["edges"].append(
                        {
                            "from": a,
                            "to": b,
                            "basis": "bound_provider_sequence",
                            "provider": evidence["provider"],
                        }
                    )
            dag = resolve_order(original, report["edges"])
            report["dag"] = dag
            if dag["status"] != "PROVEN":
                raise DemoError(dag["reason"])
            # Geometry section membership must stay contiguous after all constraints.
            if dag["order"] != selected:
                raise DemoError("COLUMN_SECTION_ORDER_CONFLICT")
            report["selected_order"] = selected
            if any(len(b["columns"]) > 1 for b in report["bands"]):
                report["status"] = "APPLIED"
                page["reading_order"] = selected
            elif any(b["reason"] for b in report["bands"]):
                report["status"] = "ABSTAIN"
        except (DemoError, ValueError, KeyError) as exc:
            report.update(
                status="ABSTAIN",
                reason=str(exc) if isinstance(exc, DemoError) else "INVALID_COLUMN_EVIDENCE",
                selected_order=original,
            )
            page["reading_order"] = original
        if report["status"] == "ABSTAIN" or any(b.get("reason") for b in report["bands"]):
            issue(
                result,
                "COLUMN_LAYOUT_FALLBACK",
                "分栏证据不足或顺序冲突，保留可编辑单栏局部降级。",
                [],
                page["page_index"],
            )
        report["selected_order"] = list(page["reading_order"])
        report["proof_sha256"] = json_hash(report)
    if "docvortex_structure" in result["metadata"]:
        result["metadata"]["columns_prior_shared_stage"] = result["metadata"].pop(
            "docvortex_structure"
        )
    result["metadata"]["column_layout"] = reports
    evidence = result["metadata"].setdefault("structure_evidence", {})
    for report in reports.values():
        if report["status"] == "APPLIED":
            for band in report["bands"]:
                for col in band["columns"]:
                    evidence.setdefault(col["source_ids"][0], {})["_paragraph_boundary"] = True
    assert result["relations"] == source["relations"]
    assert all(
        a["blocks"] == b["blocks"] for a, b in zip(source["pages"], result["pages"], strict=True)
    )
    validate(result)
    return result


def column_sections(document: Json, output: Json) -> None:
    """Split output sections at proven bands, leaving content and source geometry untouched."""
    reports = document["metadata"].get("column_layout", {})
    if not any(r["status"] == "APPLIED" for r in reports.values()):
        return
    pages = {p["page_index"]: p for p in document["pages"]}
    sections = []
    for base in output["sections"]:
        if not any(
            reports.get(str(p), {}).get("status") == "APPLIED" for p in base["source_pages"]
        ):
            sections.append(base)
            continue
        page_of = {b["id"]: pi for pi in base["source_pages"] for b in pages[pi]["blocks"]}
        if any(len({page_of[bid] for bid in n["source_ids"]}) > 1 for n in base["nodes"]):
            output["issues"].append(
                {"code": "COLUMN_SHARED_CROSS_PAGE_NODE_SINGLE_COLUMN", "source_ids": list(page_of)}
            )
            sections.append(base)
            continue
        for pi in base["source_pages"]:
            page = pages[pi]
            by_id = {b["id"]: b for b in page["blocks"]}
            nodes = [n for n in base["nodes"] if set(n["source_ids"]) & set(by_id)]
            report = reports.get(str(pi), {})
            usable = report.get("status") == "APPLIED"
            proof = {k: v for k, v in report.items() if k != "proof_sha256"}
            if usable and (
                report.get("proof_sha256") != json_hash(proof)
                or report.get("source_blocks_sha256") != json_hash(page["blocks"])
                or report.get("selected_order") != page["reading_order"]
            ):
                usable = False
                output["issues"].append(
                    {
                        "code": "COLUMN_PROOF_STALE_SINGLE_COLUMN",
                        "source_ids": page["reading_order"],
                    }
                )
            bands: list[Json] = (
                report["bands"]
                if usable
                else [
                    {
                        "id": f"p{pi}-single",
                        "columns": [
                            {
                                "source_ids": page["reading_order"],
                                "bbox": [0, 0, page["width_pt"], page["height_pt"]],
                            }
                        ],
                    }
                ]
            )
            membership = {
                bid: (bi, ci)
                for bi, band in enumerate(bands)
                for ci, c in enumerate(band["columns"])
                for bid in c["source_ids"]
            }
            if any(
                len({membership.get(bid) for bid in n["source_ids"]}) != 1
                or any(bid not in by_id for bid in n["source_ids"])
                for n in nodes
            ):
                # A shared cross-page/group node cannot be split without changing its semantics.
                output["issues"].append(
                    {
                        "code": "COLUMN_FLOW_GROUP_BOUNDARY_UNSUPPORTED",
                        "source_ids": page["reading_order"],
                    }
                )
                if base not in sections:
                    sections.append(base)
                break
            for band in bands:
                cols = band["columns"]
                band_ids = [bid for c in cols for bid in c["source_ids"]]
                chosen = [copy.deepcopy(n) for n in nodes if set(n["source_ids"]) <= set(band_ids)]
                if not chosen:
                    continue
                available = base["page_size_pt"][0] - base["margins_pt"][0] - base["margins_pt"][2]
                boxes = [c["bbox"] for c in cols]
                scale = available / (boxes[-1][2] - boxes[0][0]) if len(cols) > 1 else 1.0
                widths = [(b[2] - b[0]) * scale for b in boxes] if len(cols) > 1 else [available]
                gaps = [(b[0] - a[2]) * scale for a, b in pairwise(boxes)]
                first_seen: set[int] = set()
                for node in chosen:
                    ci = membership[node["source_ids"][0]][1]
                    node["band_id"] = band["id"]
                    node["column_index"] = ci
                    node["column_break_before"] = ci > 0 and ci not in first_seen
                    first_seen.add(ci)
                    if len(cols) > 1:
                        original = by_id[node["source_ids"][0]]
                        hint = (
                            document["metadata"]
                            .get("native_paragraph_layout", {})
                            .get(original["id"], {})
                        )
                        left = hint.get("body_left_pt", original["bbox"][0])
                        node["indent_pt"] = max(
                            0, min(widths[ci] * 0.25, (left - boxes[ci][0]) * scale)
                        )
                        node["width_pt"] = (
                            min(node["width_pt"], widths[ci] - node["indent_pt"])
                            if node["kind"] == "Figure"
                            else widths[ci] - node["indent_pt"]
                        )
                section = copy.deepcopy(base)
                section.update(
                    id=f"{base['id']}-{band['id']}",
                    source_pages=[pi],
                    nodes=chosen,
                    band_id=band["id"],
                    source_band_ids=[band["id"]],
                    column_widths_pt=widths,
                    column_gaps_pt=gaps,
                    break_type="continuous"
                    if sections and sections[-1]["source_pages"][-1] == pi
                    else "next_page",
                )
                sections.append(section)
    compact: list[Json] = []
    for section in sections:
        if (
            compact
            and section.get("break_type") == "continuous"
            and len(section.get("column_widths_pt", [])) == 1
            and len(compact[-1].get("column_widths_pt", [])) == 1
            and section["source_pages"] == compact[-1]["source_pages"]
            and section["geometry_key"] == compact[-1]["geometry_key"]
        ):
            compact[-1]["nodes"].extend(section["nodes"])
            compact[-1]["source_band_ids"].extend(section["source_band_ids"])
        else:
            compact.append(section)
    output["sections"] = compact


def verify_selected_order(before: Json, after: Json) -> None:
    """Verify that shared mapping retained exactly the selected order and all block payloads."""
    for a, b in zip(before["pages"], after["pages"], strict=True):
        if a["reading_order"] != b["reading_order"] or a["blocks"] != b["blocks"]:
            raise DemoError("SHARED_COLUMN_ORDER_OR_CONTENT_CHANGED")
