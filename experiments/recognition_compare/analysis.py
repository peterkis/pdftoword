"""Paired comparison on common reference units and explicit coverage/Word evidence tables."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-untyped]

from .common import ARMS, GROUPS, Json, digest, offline, read, source_identity, verify, write


def comparison(run: Path, evaluation: Path, output: Path) -> Json:
    """Never rank conditional CER values computed over different eligible references."""
    with offline():
        verify(run / "frozen")
        output.mkdir(parents=True, exist_ok=False)
        metrics: list[Json] = []
        by_arm: dict[str, dict[tuple[str, int, str], Json]] = {a: {} for a in ARMS}
        for group, (source, _, _) in GROUPS.items():
            for arm in ARMS:
                score_path = evaluation / group / f"{arm}-scoring.json"
                receipt_path = run / "runs" / group / arm / "receipt.json"
                receipt: Json = (
                    read(receipt_path) if receipt_path.exists() else {"status": "NOT_RUN"}
                )
                row: Json = {
                    "group": group,
                    "source": source,
                    "arm": arm,
                    "status": receipt["status"],
                    "source_pages": len(GROUPS[group][1]),
                    "word_pages": None,
                    "word_open": "NOT_RUN",
                    "python_model_calls": receipt.get("model_calls", 0) if arm == "A" else None,
                    "online_file_submissions": receipt.get("parse_submissions", 0)
                    if arm != "A"
                    else 0,
                    "online_internal_model_calls": "unknown" if arm != "A" else None,
                    "visual_acceptance": "PENDING",
                    "score_reference": "mixed owner and agent evidence",
                }
                pdf = run / "word-review" / f"{group}-{arm}.pdf"
                native_pdf = run / "word-review" / f"{group}-{arm}-clean-native.pdf"
                clean_pdf = run / "word-review" / f"{group}-{arm}-clean.pdf"
                if native_pdf.exists():
                    pdf = native_pdf
                elif clean_pdf.exists():
                    pdf = clean_pdf
                if pdf.exists():
                    doc = pdfium.PdfDocument(pdf)
                    row.update(
                        word_pages=len(doc), word_open="EXECUTED", word_pdf_sha256=digest(pdf)
                    )
                    doc.close()
                row.update(receipt.get("docx_inventory", {}))
                if score_path.exists():
                    score = read(score_path)
                    matches = [m for p in score["pages"] for m in p["matches"]]
                    for kind in ("text", "formula", "table", "image"):
                        counts = Counter(
                            m["status"] for m in matches if m["reference"]["kind"] == kind
                        )
                        for state in (
                            "MATCHED",
                            "MISSING",
                            "ALIGNMENT_REVIEW",
                            "REFERENCE_EXCLUDED",
                        ):
                            row[f"{kind}_{state.lower()}"] = counts[state]
                    for flag in (True, False):
                        row["formula_structure_" + str(flag)] = sum(
                            m.get("structure_equal") is flag for m in matches
                        )
                    row["formula_structure_unscored"] = sum(
                        m["reference"]["kind"] == "formula" and m.get("structure_equal") is None
                        for m in matches
                    )
                    cells = [c for m in matches for c in m.get("table", {}).get("cells", [])]
                    row["table_cells_scored"] = len(cells)
                    row["table_cells_text_equal"] = sum(c["text_equal"] for c in cells)
                    row["table_cells_span_equal"] = sum(c["span_equal"] for c in cells)
                    edges = Counter(
                        e["status"] for p in score["pages"] for e in p["reading_order_edges"]
                    )
                    row.update({"order_" + k.lower(): v for k, v in edges.items()})
                    row["discarded_units"] = sum(len(p["discarded"]) for p in score["pages"])
                    row["unmatched_output_units_needing_review"] = sum(
                        len(p["unmatched_outputs"]) for p in score["pages"]
                    )
                    row["route_not_provided"] = sum(
                        p["actual_route"] == "NOT_PROVIDED" for p in score["pages"]
                    )
                    row["route_disagreements"] = sum(
                        p["actual_route"] not in {"NOT_PROVIDED", p["expected_route"]}
                        for p in score["pages"]
                    )
                    for page in score["pages"]:
                        if not page["aggregate_content"]:
                            continue
                        for match in page["matches"]:
                            if "cer" in match:
                                key = (source, page["original_page"], match["reference"]["id"])
                                by_arm[arm][key] = match
                metrics.append(row)
        paired = []
        for left, right in (("A", "B"), ("A", "C"), ("B", "C")):
            common = by_arm[left].keys() & by_arm[right].keys()
            for human in (False, True):
                selected = [
                    key
                    for key in sorted(common)
                    if by_arm[left][key]["reference"]["human_confirmed"] == human
                ]
                sources: Json = {}
                for key in selected:
                    record = sources.setdefault(
                        key[0],
                        {"reference_chars": 0, "left_distance": 0, "right_distance": 0, "units": 0},
                    )
                    a, b = by_arm[left][key]["cer"], by_arm[right][key]["cer"]
                    if a["reference_chars"] != b["reference_chars"]:
                        raise ValueError("PAIRED_REFERENCE_CHANGED")
                    record["reference_chars"] += a["reference_chars"]
                    record["left_distance"] += a["distance"]
                    record["right_distance"] += b["distance"]
                    record["units"] += 1
                for data in sources.values():
                    for side in ("left", "right"):
                        data[side + "_cer"] = (
                            data[side + "_distance"] / data["reference_chars"]
                            if data["reference_chars"]
                            else None
                        )
                paired.append(
                    {
                        "left": left,
                        "right": right,
                        "owner_confirmed": human,
                        "common_unit_count": len(selected),
                        "sources": sources,
                        "left_total_scorable_units": len(by_arm[left]),
                        "right_total_scorable_units": len(by_arm[right]),
                        "claim_scope": "conditional common subset, not whole-corpus accuracy",
                    }
                )
        with (output / "metrics.csv").open("w") as stream:
            fields = list(dict.fromkeys(k for r in metrics for k in r))
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(metrics)
        result = {
            "metrics": metrics,
            "paired_text": paired,
            "model_calls": 0,
            "evaluator_identity": source_identity(),
            "input_evaluation": str(evaluation.relative_to(run)),
            "evaluator_note": (
                "Adds common-denominator comparisons; raw runs and prior scores unchanged"
            ),
        }
        write(output / "comparison.json", result)
        return result
