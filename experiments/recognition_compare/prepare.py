"""Freeze owner edits and lossless source-page subsets before any model call."""

from __future__ import annotations

import copy
import hashlib
import re
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium  # type: ignore[import-untyped]

from .common import (
    GROUPS,
    ROOT,
    ExperimentError,
    Json,
    digest,
    load_local_environment,
    now,
    quiet_upstream,
    read,
    seal,
    source_identity,
    verify,
    write,
)

# Stable anchors from the supplied review queue; policies are explicit owner decisions.
IMAGE_ONLY = {
    "c0981cd4c71952a3ba9466743ee3f064",  # Confirmed in the plan conversation.
}


def nodes(value: Any) -> Iterator[Json]:
    """Walk all duplicated references, including cells and formula records."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def apply_edits(annotation: Json, edits: list[Json]) -> tuple[Json, list[Json]]:
    """Apply bound edits to a copy, retaining notes separately from source text."""
    result = copy.deepcopy(annotation)
    changes = []
    for edit in edits:
        if edit["sample_id"] != annotation["sample_id"]:
            continue
        page = next((p for p in result["pages"] if p["page"] == edit["page"]), None)
        if page is None or not any(a["id"] == edit["anchor_id"] for a in page["anchors"]):
            raise ExperimentError("EDIT_ANCHOR_OR_PAGE_MISMATCH")
        note = edit.get("note", "")
        policy = "score"
        if any(
            s in note
            for s in [
                "图的一部分",
                "图片的一部分",
                "整体图",
                "非文本",
                "保持原始图",
                "保留原始图",
                "不做文字识别",
                "和图片作为一个",
            ]
        ):
            policy = "preserve_image"
        if "裁切，抛弃" in note or "扫描问题" in note:
            policy = "source_truncated_unscored"
        before = []
        for node in nodes(page):
            if node.get("anchor_id", node.get("id")) != edit["anchor_id"]:
                continue
            before.append(copy.deepcopy(node))
            if "text" in edit and "text" in node:
                node["text"] = edit["text"]
                if "text_lines" in node:
                    node["text_lines"] = edit["text"].splitlines()
            if "bbox" in node and edit.get("bbox") is not None:
                node["bbox"] = edit["bbox"]
            node["comparison_review"] = {
                "source": "owner_export",
                "decision": edit["decision"],
                "policy": policy,
                "note": note,
            }
        changes.append(
            {"anchor_id": edit["anchor_id"], "before": before, "edit": edit, "policy": policy}
        )
    for page in result["pages"]:
        for node in nodes(page):
            if node.get("anchor_id", node.get("id")) in IMAGE_ONLY:
                node["comparison_review"] = {
                    "source": "owner_plan_confirmation",
                    "policy": "preserve_image",
                }
        if annotation["source"]["uploaded_filename"] == "native.pdf":
            page["comparison_route"] = "native" if page["page"] == 7 else "mixed"
            page["comparison_route_basis"] = "owner_plan_confirmation"
        else:
            page["comparison_route"] = "scan"
        if annotation["source"]["uploaded_filename"] == "scan.pdf" and page["page"] == 9:
            page["comparison_continuation"] = {
                "previous_original_page": 8,
                "logical_columns": 3,
                "column_assignment": ["factorization:left", "middle:second", "exercise:right"],
                "basis": "owner_export",
                "geometry": "REQUIRES_SOURCE_ALIGNED_REVIEW",
                "legacy_two_region_grid_is_not_three_column_truth": True,
            }
            for table in page["tables"]:
                table["comparison_grid_status"] = "LOGICAL_THREE_COLUMNS_GEOMETRY_UNRESOLVED"
    return result, changes


def subset(source: Path, pages: list[int], target: Path, image_dir: Path) -> list[Json]:
    """Copy PDF pages as native objects and prove rendered pixels unchanged."""
    source_pdf = pdfium.PdfDocument(source)
    selected = pdfium.PdfDocument.new()
    selected.import_pages(source_pdf, [p - 1 for p in pages])
    selected.save(target)
    selected.close()
    reopened = pdfium.PdfDocument(target)
    rows = []
    image_dir.mkdir(parents=True)
    for index, original in enumerate(pages):
        left, right = source_pdf[original - 1], reopened[index]
        a, b = left.render(scale=2).to_pil(), right.render(scale=2).to_pil()
        if a.size != b.size or a.tobytes() != b.tobytes():
            raise ExperimentError("SUBSET_RENDER_CHANGED")
        b.save(image_dir / f"page-{index + 1}.png")
        rows.append(
            {
                "input_page": index + 1,
                "original_page": original,
                "size_pt": list(right.get_size()),
                "pixel_size": list(b.size),
                "pixels_sha256": hashlib.sha256(b.tobytes()).hexdigest(),
            }
        )
        left.close()
        right.close()
    reopened.close()
    source_pdf.close()
    return rows


def prepare(dataset: Path, edits_path: Path, run: Path) -> Json:
    """Prepare all six groups and freeze A's complete request budget without inference."""
    run = run.resolve()
    if not run.is_relative_to(ROOT / "tmp/docx-demo"):
        raise ExperimentError("PRIVATE_RUN_ROOT_REQUIRED")
    run.mkdir(mode=0o700, parents=True, exist_ok=False)
    dest = run / "frozen"
    dest.mkdir()
    manifest, edits = read(dataset / "manifest.v7.json"), read(edits_path)
    expected = [
        {k: s[k] for k in ("sample_id", "source_sha256", "selected_pages")}
        for s in manifest["samples"]
    ]
    if edits["source_binding"] != expected or edits["base_manifest_version"] != 7:
        raise ExperimentError("REVIEW_SOURCE_BINDING_MISMATCH")
    if len({e["anchor_id"] for e in edits["edits"]}) != len(edits["edits"]):
        raise ExperimentError("DUPLICATE_REVIEW_ANCHOR")
    refs = {}
    changes = []
    sources = {}
    for sample in manifest["samples"]:
        name = Path(sample["source_filename"]).stem
        source = dataset / sample["source_filename"]
        if digest(source) != sample["source_sha256"]:
            raise ExperimentError("SOURCE_HASH_MISMATCH")
        annotation = read(dataset / sample["annotation_file"])
        refs[name], changed = apply_edits(annotation, edits["edits"])
        changes.extend(changed)
        sources[name] = {
            "sha256": digest(source),
            "annotation_sha256": digest(dataset / sample["annotation_file"]),
        }
    if len(changes) != len(edits["edits"]):
        raise ExperimentError("UNAPPLIED_REVIEW_EDIT")
    write(
        dest / "review-merge.json",
        {
            "edits": changes,
            "global_human_acceptance": "PENDING",
            "review_export_sha256": digest(edits_path),
            "owner_plan_confirmations": [
                "native page 7 native; other selected native pages mixed",
                "supermix page 5 blurred image lettering preserved with image",
            ],
        },
    )
    shutil.copyfile(edits_path, dest / "owner-edits.json")
    write(dest / "references.json", refs)
    groups: Json = {}
    load_local_environment()
    from prototypes.docx_output.pipeline import convert

    for key, (name, pages, language) in GROUPS.items():
        folder = dest / key
        folder.mkdir()
        rows = subset(dataset / f"{name}.pdf", pages, folder / "input.pdf", folder / "source-pages")
        with quiet_upstream():
            try:
                job = convert(
                    folder / "input.pdf",
                    mode="auto",
                    output_root=run / "project-jobs",
                    content_provider="ovis-pp",
                    auto_profile="reconstruction-v2",
                )
                plan = read(job / "route-plan.json")
                a = {
                    "status": "PREPARED",
                    "job": job.relative_to(run).as_posix(),
                    "plan_hash": plan["plan_hash"],
                    "budget": plan["request_budget"],
                }
                shutil.copyfile(job / "route-plan.json", folder / "A-route-plan.json")
            except Exception as exc:
                a = {
                    "status": "PREPARE_FAILED",
                    "error_type": type(exc).__name__,
                    "error": str(exc) if re.fullmatch(r"[A-Z_0-9]+", str(exc)) else "PREPARE_ERROR",
                }
        groups[key] = {
            "file": name,
            "pages": pages,
            "language": language,
            "page_map": rows,
            "input_sha256": digest(folder / "input.pdf"),
            "A": a,
        }
    record = {
        "schema": "p2w-three-arm/1",
        "created_at": now(),
        "groups": groups,
        "sources": sources,
        "source_identity": source_identity(),
        "A_total_budget": sum(g["A"].get("budget", 0) for g in groups.values()),
        "online_parse_files": 12,
        "online_pages": 58,
        "excluded_pages": {"mix": [1, 3], "scan": [3]},
        "derived_content": {
            "secondary": "mix:4",
            "primary": "native:2",
            "policy": "secondary page content diagnostic only; layout retained",
        },
        "reference_scope": "owner_confirmed_items_plus_agent_draft_not_global_gold",
        "scoring_policy": {
            "normalization": "NFC and line endings only",
            "retries": 0,
            "matching": "geometry first; ambiguity remains unscored",
            "sum_score": False,
        },
    }
    write(dest / "manifest.json", record)
    seal(dest)
    return record


def extend_page_limit(previous: Path, run: Path) -> Json:
    """Create a separate authorized G2/G3 first-inference cohort; retain old evidence."""
    previous, run = previous.resolve(), run.resolve()
    verify(previous / "frozen")
    original = read(previous / "frozen/manifest.json")
    for group in ("G2", "G3"):
        if original["groups"][group]["A"].get("error") != "MAX_THREE_PAGES":
            raise ExperimentError("NOT_A_PAGE_LIMIT_BLOCK")
        prior = read(previous / "runs" / group / "A/receipt.json")
        if prior.get("model_calls") != 0 or (previous / "runs" / group / "A/artifacts").exists():
            raise ExperimentError("PRIOR_INFERENCE_CANNOT_BE_REPEATED")
    run.mkdir(parents=True, exist_ok=False, mode=0o700)
    shutil.copytree(previous / "frozen", run / "frozen", ignore=shutil.ignore_patterns("seal.json"))
    for group in GROUPS:
        for arm in ("A", "B", "C"):
            if arm == "A" and group in {"G2", "G3"}:
                continue
            folder = previous / "runs" / group / arm
            verify(folder / "artifacts")
            shutil.copytree(folder, run / "runs" / group / arm)
    load_local_environment()
    from prototypes.docx_output.pipeline import convert

    for group in ("G2", "G3"):
        limit = len(GROUPS[group][1])
        with quiet_upstream():
            job = convert(
                run / "frozen" / group / "input.pdf",
                mode="auto",
                output_root=run / "project-jobs",
                content_provider="ovis-pp",
                auto_profile="reconstruction-v2",
                page_limit=limit,
            )
        plan = read(job / "route-plan.json")
        original["groups"][group]["A"] = {
            "status": "PREPARED",
            "job": job.relative_to(run).as_posix(),
            "plan_hash": plan["plan_hash"],
            "budget": plan["request_budget"],
            "page_limit": limit,
        }
        shutil.copyfile(job / "route-plan.json", run / "frozen" / group / "A-route-plan.json")
    original["amendment"] = {
        "reason": "Owner authorized page-limit override; G2/G3 had zero inference",
        "previous_run": previous.name,
        "previous_manifest_sha256": digest(previous / "frozen/manifest.json"),
        "inherited_source_identity": original["source_identity"],
        "new_inference_groups": ["G2", "G3"],
        "new_inference_arm": "A",
        "new_request_budget": sum(original["groups"][g]["A"]["budget"] for g in ("G2", "G3")),
        "created_at": now(),
    }
    original["source_identity"] = source_identity()
    original["A_total_budget"] = sum(g["A"]["budget"] for g in original["groups"].values())
    write(run / "frozen/manifest.json", original)
    seal(run / "frozen")
    return original
