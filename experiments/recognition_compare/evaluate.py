"""Offline common geometry-first evaluation; unresolved alignment is not correctness."""

from __future__ import annotations

import copy
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path

from lxml import etree, html

from acceptance.formula import reference_tree
from acceptance.metrics import cer

from .common import ARMS, GROUPS, ExperimentError, Json, inspect_docx, offline, read, verify, write


def norm(value: str) -> str:
    """Preserve punctuation, digits, case and whitespace except line-ending encoding."""
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


def area(box: list[float]) -> float:
    """Return the area of a valid rectangular region."""
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def overlap(a: list[float], b: list[float]) -> float:
    """Intersection area in source PDF points."""
    return area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])


def grid_from_html(value: str) -> Json:
    """Read actual HTML cell topology, including blank and merged cells."""
    try:
        root = html.fragment_fromstring(value, create_parent="div")
        rows = root.xpath(".//table[not(ancestor::table)]//tr[not(ancestor::tr)]")
        cells: list[Json] = []
        occupied: set[tuple[int, int]] = set()
        columns = 0
        for r, row in enumerate(rows):
            c = 0
            for cell in row.xpath("./td | ./th"):
                while (r, c) in occupied:
                    c += 1
                rs, cs = int(cell.get("rowspan", "1")), int(cell.get("colspan", "1"))
                if not (0 < rs < 1000 and 0 < cs < 1000):
                    raise ValueError("invalid span")
                cells.append(
                    {"row": r, "col": c, "rowspan": rs, "colspan": cs, "text": cell.text_content()}
                )
                occupied.update((y, x) for y in range(r, r + rs) for x in range(c, c + cs))
                columns = max(columns, c + cs)
                c += cs
        return {"rows": len(rows), "columns": columns, "cells": cells}
    except (ValueError, etree.ParserError) as exc:
        raise ExperimentError("TABLE_HTML_UNSUPPORTED") from exc


def normalized_output(artifacts: Path, arm: str, group: Json) -> Json:
    """Adapt real observed schemas only; never force old online JSON into SDK 4.0 types."""
    units: list[Json] = []
    pages: list[Json] = []
    metadata: Json = {}
    if arm == "A":
        data = read(artifacts / "project/layout.auto.json")
        metadata["relations"] = data.get("relations", [])
        for page in data["pages"]:
            pi = page["page_index"]
            pages.append({"page": pi + 1, "route": page.get("page_type", "unknown")})
            order = {value: i for i, value in enumerate(page["reading_order"])}
            for block in page["blocks"]:
                content = block.get("content", {})
                kind = block["type"]
                text = content.get("plain_text", content.get("text", content.get("latex", "")))
                if not isinstance(text, str):
                    text = ""
                unit = {
                    "id": block["id"],
                    "page": pi + 1,
                    "bbox": block["bbox"],
                    "kind": "formula"
                    if kind in {"formula", "equation"}
                    else "table"
                    if kind == "table"
                    else "image"
                    if kind in {"figure", "image"} or content.get("kind") == "image"
                    else "text",
                    "text": norm(text),
                    "order": order.get(block["id"], len(order)),
                    "raw_kind": kind,
                    "raw": copy.deepcopy(block),
                    "discarded": False,
                }
                if content.get("html"):
                    unit["grid"] = grid_from_html(content["html"])
                elif kind == "table" and content.get("cells"):
                    unit["grid"] = content
                units.append(unit)
    else:
        files = list((artifacts / "result").rglob("layout.json"))
        if len(files) != 1:
            raise ExperimentError("ONLINE_LAYOUT_MISSING_OR_AMBIGUOUS")
        data = read(files[0])
        if not isinstance(data.get("pdf_info"), list):
            raise ExperimentError("ONLINE_LAYOUT_SCHEMA_UNSUPPORTED")
        metadata = {k: data.get(k, "unknown") for k in ("_backend", "_version_name", "_effort")}
        metadata["relations"] = "NOT_PROVIDED"
        for pi, page in enumerate(data["pdf_info"]):
            if page.get("page_idx", pi) != pi:
                raise ExperimentError("ONLINE_PAGE_MAPPING_UNSUPPORTED")
            source_size = group["page_map"][pi]["size_pt"]
            size = page["page_size"]
            sx, sy = source_size[0] / size[0], source_size[1] / size[1]
            pages.append({"page": pi + 1, "route": "NOT_PROVIDED"})

            def walk(
                block: Json, discarded: bool, pi: int = pi, sx: float = sx, sy: float = sy
            ) -> None:
                for child in block.get("blocks", []):
                    walk(child, discarded)
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        box = span.get("bbox", line.get("bbox", block.get("bbox")))
                        if not isinstance(box, list) or len(box) != 4:
                            raise ExperimentError("ONLINE_SPAN_GEOMETRY_MISSING")
                        kind = span.get("type", "text")
                        text = span.get("content", "")
                        unit: Json = {
                            "id": f"p{pi + 1}-u{len(units)}",
                            "page": pi + 1,
                            "bbox": [box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy],
                            "kind": "formula"
                            if "equation" in kind
                            else "table"
                            if kind == "table"
                            else "image"
                            if kind == "image"
                            else "text",
                            "raw_kind": kind,
                            "text": norm(text) if isinstance(text, str) else "",
                            "order": len(units),
                            "discarded": discarded,
                            "raw": span,
                        }
                        if span.get("html"):
                            unit["grid"] = grid_from_html(span["html"])
                        units.append(unit)

            for block in page.get("para_blocks", []):
                walk(block, False)
            for block in page.get("discarded_blocks", []):
                walk(block, True)
    return {"units": units, "pages": pages, "metadata": metadata}


def reference_units(page: Json) -> list[Json]:
    """Keep scoring units separate from contextual formula indexes and image text."""
    anchors = {a["id"]: a for a in page["anchors"]}
    result: list[Json] = []
    for collection, kind in (
        ("blocks", "text"),
        ("formulas", "formula"),
        ("tables", "table"),
        ("figures", "image"),
    ):
        for item in page[collection]:
            if collection == "blocks" and item.get("kind") == "table_cell":
                continue
            anchor = anchors.get(item["anchor_id"], {})
            review = item.get("comparison_review", anchor.get("comparison_review", {}))
            policy = review.get("policy", "score")
            if "context" in item.get("subtype", ""):
                policy = "context_only"
            status = item.get("evidence_status", anchor.get("evidence_status", "unknown"))
            if policy == "score" and status == "uncertain" and not review:
                policy = "unresolved_reference"
            result.append(
                {
                    "id": item["anchor_id"],
                    "bbox": item.get("bbox", anchor.get("bbox")),
                    "kind": kind,
                    "text": norm(item.get("text", "")),
                    "policy": policy,
                    "human_confirmed": bool(review),
                    "raw_kind": item.get("kind", kind),
                    "raw": item,
                }
            )
    return result


def align(refs: list[Json], outputs: list[Json]) -> list[Json]:
    """Assign output by geometry only, reserving ties and fused spans for adjudication."""
    assigned: dict[str, list[Json]] = {r["id"]: [] for r in refs}
    ambiguity: dict[str, list[str]] = {r["id"]: [] for r in refs}
    for out in outputs:
        if out["discarded"]:
            continue
        candidates = []
        for ref in refs:
            if ref["policy"] != "score" or ref["kind"] != out["kind"] or not ref["bbox"]:
                continue
            inter = overlap(ref["bbox"], out["bbox"])
            fraction = inter / max(0.001, min(area(ref["bbox"]), area(out["bbox"])))
            if fraction >= 0.5:
                candidates.append((fraction, ref))
        candidates.sort(key=lambda x: -x[0])
        if len(candidates) == 1:
            assigned[candidates[0][1]["id"]].append(out)
        elif len(candidates) > 1:
            for _, ref in candidates:
                ambiguity[ref["id"]].append(out["id"])
    result = []
    for ref in refs:
        matched_outputs = sorted(assigned[ref["id"]], key=lambda x: x["order"])
        state = "MATCHED" if matched_outputs else "MISSING"
        if ambiguity[ref["id"]]:
            state = "ALIGNMENT_REVIEW"
        if ref["policy"] != "score":
            state = "REFERENCE_EXCLUDED"
        result.append(
            {
                "reference": ref,
                "outputs": matched_outputs,
                "status": state,
                "ambiguous_output_ids": ambiguity[ref["id"]],
            }
        )
    return result


def table_comparison(ref: Json, predicted: Json) -> Json:
    """Compare matched logical cells; preserve empty/merged-cell denominators."""
    cells = {(c["row"], c["col"]): c for c in predicted.get("cells", [])}
    checks = []
    for cell in ref["cells"]:
        other = cells.get((cell["row"], cell["col"]))
        checks.append(
            {
                "anchor_id": cell["anchor_id"],
                "missing": other is None,
                "text_equal": other is not None and norm(cell["text"]) == norm(other["text"]),
                "span_equal": other is not None
                and all(cell.get(k, 1) == other.get(k, 1) for k in ("rowspan", "colspan")),
                "blank": not cell["text"],
            }
        )
    return {
        "rows_equal": ref["rows"] == predicted.get("rows"),
        "columns_equal": ref["columns"] == predicted.get("columns"),
        "cells": checks,
    }


def score_page(page: Json, predicted: list[Json]) -> Json:
    """Evaluate without removing missing units or treating unsupported structure as success."""
    matches = align(reference_units(page), predicted)
    for match in matches:
        ref, out = match["reference"], match["outputs"]
        if match["status"] not in {"MATCHED", "MISSING"}:
            continue
        text = "".join(u["text"] for u in out)
        if ref["kind"] == "text":
            match["cer"] = cer(ref["text"], text)
        if ref["kind"] == "formula":
            left, right = reference_tree(ref["text"]), reference_tree(text)
            match["exact_text"] = ref["text"] == text
            match["structure_equal"] = (
                left == right if left is not None and right is not None else None
            )
            match["formula_structure_status"] = (
                "SCORED" if left and right else "GRAMMAR_UNSUPPORTED_OR_MISSING"
            )
        if ref["kind"] == "table":
            if ref["raw"].get("comparison_grid_status"):
                match["table_status"] = "OWNER_LOGICAL_COLUMNS_REQUIRE_GEOMETRY_REVIEW"
            elif len(out) == 1 and "grid" in out[0]:
                match["table"] = table_comparison(ref["raw"], out[0]["grid"])
            else:
                match["table_status"] = "MISSING" if not out else "GRID_UNSUPPORTED"
    positions = {
        m["reference"]["id"]: (
            min(x["order"] for x in m["outputs"]),
            max(x["order"] for x in m["outputs"]),
        )
        for m in matches
        if m["status"] == "MATCHED" and m["outputs"]
    }
    edges = []
    for edge in page.get("reading_order_edges", []):
        a, b = edge["from"], edge["to"]
        state = "MISSING_OR_UNALIGNED"
        if a in positions and b in positions:
            state = "SATISFIED" if positions[a][1] < positions[b][0] else "REVERSED_OR_OVERLAPPED"
        edges.append({**edge, "status": state})
    used = {o["id"] for m in matches for o in m["outputs"]}
    uncertain = {o for m in matches for o in m["ambiguous_output_ids"]}
    return {
        "matches": matches,
        "reading_order_edges": edges,
        "unmatched_outputs": [
            o for o in predicted if not o["discarded"] and o["id"] not in used | uncertain
        ],
        "discarded": [o for o in predicted if o["discarded"]],
        "relation_reference": page.get("relationships", []),
        "relation_scoring": "REQUIRES_EXPLICIT_OUTPUT_RELATION_OR_VISUAL_ADJUDICATION",
    }


def docx_units(path: Path) -> Json:
    """Read actual OOXML content, styles, sections and objects without editing the package."""
    ns = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    }
    with zipfile.ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
        paragraphs = []
        for i, p in enumerate(root.xpath("//w:body//w:p", namespaces=ns)):
            paragraphs.append(
                {
                    "index": i,
                    "text": norm("".join(p.xpath(".//w:t/text()", namespaces=ns))),
                    "math": len(p.xpath(".//m:oMath", namespaces=ns)),
                    "images": len(p.xpath(".//w:drawing", namespaces=ns)),
                    "in_table": bool(p.xpath("ancestor::w:tbl", namespaces=ns)),
                    "style": p.xpath("./w:pPr/w:pStyle/@w:val", namespaces=ns),
                }
            )
        sections = [etree.tostring(s).decode() for s in root.xpath("//w:sectPr", namespaces=ns)]
        edge_parts = {
            n: "".join(etree.fromstring(archive.read(n)).xpath("//w:t/text()", namespaces=ns))
            for n in archive.namelist()
            if n.startswith(("word/header", "word/footer")) and n.endswith(".xml")
        }
    return {
        "paragraphs": paragraphs,
        "sections": sections,
        "header_footer": edge_parts,
        "inventory": inspect_docx(path.read_bytes()),
    }


def docx_alignment(pages: list[Json], docx: Json) -> list[Json]:
    """Map already geometrically bound recognition text to OOXML; duplicates stay ambiguous."""
    results = []
    paragraphs = docx["paragraphs"]
    for page in pages:
        for match in page["matches"]:
            if match["status"] != "MATCHED" or match["reference"]["kind"] != "text":
                continue
            text = "".join(o["text"] for o in match["outputs"])
            candidates = []
            if text:
                for i, paragraph in enumerate(paragraphs):
                    if text in paragraph["text"]:
                        candidates.append([i])
                    for size in range(2, 5):
                        group = paragraphs[i : i + size]
                        if len(group) == size and "".join(p["text"] for p in group) == text:
                            candidates.append(list(range(i, i + size)))
            results.append(
                {
                    "anchor_id": match["reference"]["id"],
                    "candidate_paragraphs": candidates,
                    "status": "TEXT_BOUND" if len(candidates) == 1 else "ALIGNMENT_REVIEW",
                    "evidence": "recognition_geometry_then_exact_ooxml_text",
                    "original_page": page["original_page"],
                }
            )
    return results


def evaluate(run: Path, output: Path) -> Json:
    """Recompute from sealed outputs under a Python network deny guard, with no converter import."""
    with offline():
        verify(run / "frozen")
        manifest = read(run / "frozen/manifest.json")
        refs = read(run / "frozen/references.json")
        output.mkdir(parents=True, exist_ok=False)
        summary = []
        for group_name in GROUPS:
            group = manifest["groups"][group_name]
            for arm in ARMS:
                folder = run / "runs" / group_name / arm
                if not (folder / "receipt.json").exists():
                    summary.append({"group": group_name, "arm": arm, "status": "NOT_RUN"})
                    continue
                receipt = read(folder / "receipt.json")
                artifacts = folder / "artifacts"
                if not (artifacts / "seal.json").exists():
                    summary.append({"group": group_name, "arm": arm, "status": receipt["status"]})
                    continue
                try:
                    verify(artifacts)
                    predicted = normalized_output(artifacts, arm, group)
                    results = []
                    for pi, original in enumerate(group["pages"]):
                        page = next(
                            p for p in refs[group["file"]]["pages"] if p["page"] == original
                        )
                        result = score_page(
                            page, [u for u in predicted["units"] if u["page"] == pi + 1]
                        )
                        result.update(
                            original_page=original,
                            input_page=pi + 1,
                            aggregate_content=not (group["file"] == "mix" and original == 4),
                            expected_route=page["comparison_route"],
                            actual_route=predicted["pages"][pi]["route"],
                        )
                        results.append(result)
                    docx_path = artifacts / ("A.docx" if arm == "A" else "B.docx")
                    package = docx_units(docx_path)
                    aligned = docx_alignment(results, package)
                    all_matches = [
                        m for p in results if p["aggregate_content"] for m in p["matches"]
                    ]
                    item = {
                        "group": group_name,
                        "arm": arm,
                        "status": receipt["status"],
                        "alignment_counts": dict(Counter(m["status"] for m in all_matches)),
                        "docx_inventory": package["inventory"],
                        "word_open": receipt["word_open"],
                        "source_pages": len(group["pages"]),
                        "model_calls": receipt.get("model_calls"),
                        "docx_alignment": dict(Counter(m["status"] for m in aligned)),
                        "human_reference_units": sum(
                            m["reference"]["human_confirmed"] for m in all_matches
                        ),
                    }
                    for label, human in (("owner", True), ("agent", False)):
                        scored = [
                            m["cer"]
                            for m in all_matches
                            if "cer" in m and m["reference"]["human_confirmed"] == human
                        ]
                        item[label + "_cer_records"] = scored
                    write(output / group_name / f"{arm}-recognition.json", predicted)
                    write(output / group_name / f"{arm}-scoring.json", {"pages": results})
                    write(
                        output / group_name / f"{arm}-word.json",
                        {
                            "package": package,
                            "alignment": aligned,
                            "visual": "NOT_RUN",
                            "editability_probe": "NOT_RUN",
                        },
                    )
                    summary.append(item)
                except Exception as exc:
                    summary.append(
                        {
                            "group": group_name,
                            "arm": arm,
                            "status": "EVALUATION_BLOCKED",
                            "error": str(exc)
                            if isinstance(exc, ExperimentError)
                            else type(exc).__name__,
                        }
                    )
        record = {
            "schema": "p2w-comparison-summary/1",
            "rows": summary,
            "network_calls": 0,
            "reference_status": manifest["reference_scope"],
            "product_acceptance": "PENDING",
        }
        write(output / "summary.json", record)
        return record
