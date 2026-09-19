"""Offline, new-job macro arbitration from a sealed source job; never calls models."""

from __future__ import annotations

import argparse
import copy
import shutil
from pathlib import Path

from .common import JOBS, DemoError, Json, crop, digest, new_job, read, safe_path, save
from .geometry.arbitrator import GeometryArbitrator
from .geometry.candidate import attach, full_page
from .geometry.pp_adapter import adapt
from .geometry.support import binding_ledger, content_support
from .render_replay import inventory, verify_source


def arbitrate_document(
    job: Path, selected: Json, evidence_dir: Path, requests: list[Json]
) -> list[Json]:
    """Use independently hashed evidence; isolate page failures without new model calls."""
    decisions = []
    for index, page in enumerate(list(selected["pages"])):
        snapshot = copy.deepcopy(selected)
        try:
            info = selected["provenance"]["pages"][str(page["page_index"])]
            chain = full_page(page, info)
            pp = None
            eligible = [
                r
                for r in requests
                if r["provider"] == "pp"
                and r["page_index"] == page["page_index"]
                and r["status"] == "COMPLETE"
            ]
            if len(eligible) == 1 and eligible[0]["input_sha256"] == digest(
                job / info["image_path"]
            ):
                entry = eligible[0]
                response = safe_path(evidence_dir, f"response-{entry['region_id']}-pp.json")
                if digest(response) != entry["stored_response_sha256"]:
                    raise DemoError("GEOMETRY_RESPONSE_HASH_MISMATCH")
                pp = read(response)
                if not any(c["provider"] == "pp" for c in page.get("geometry_candidates", [])):
                    attach(
                        page,
                        adapt(
                            pp,
                            page["page_index"],
                            chain,
                            {"response_sha256": entry["stored_response_sha256"]},
                        ),
                    )
            supports = content_support(page, chain, pp)
            selected["metadata"].setdefault("geometry_support", {})[str(page["page_index"])] = (
                supports
            )
            selected["metadata"].setdefault("source_binding_ledger", {})[
                str(page["page_index"])
            ] = binding_ledger(page, supports)
            projected, decision = GeometryArbitrator().propose(page, supports)
            if decision.get("content_proof", {}).get("column_order", {}).get("status") == "PROVEN":
                selected["metadata"].setdefault("column_order", {})[str(page["page_index"])] = (
                    decision["content_proof"]["column_order"]
                )
            for bid, support in supports.items():
                fragments = support.get("line_fragments", [])
                if fragments and not any(f["shared_line"] for f in fragments):
                    selected["metadata"].setdefault("structure_evidence", {})[bid] = {
                        "coordinate_space": "pdf_points",
                        "lines": [
                            {"bbox": f["bbox_pt"], "source_span_id": sid}
                            for f, sid in zip(fragments, support["source_span_ids"], strict=True)
                        ],
                        "source_spans": fragments,
                    }
            decision.update(
                page_index=page["page_index"],
                support_count=len(supports),
                block_count=len(page["blocks"]),
            )
            if decision["status"] == "SELECTED":
                old = {b["id"]: b for b in page["blocks"]}
                for block in projected["blocks"]:
                    if (
                        block["content"]["kind"] == "image"
                        and block["bbox"] != old[block["id"]]["bbox"]
                    ):
                        previous_asset = block["content"]["asset_id"]
                        block["content"]["asset_id"] = crop(
                            job, selected, projected, block["bbox"], block["id"] + "-arbitrated"
                        )
                        decision.setdefault("recropped", []).append(
                            {
                                "block_id": block["id"],
                                "previous_asset_id": previous_asset,
                                "asset_id": block["content"]["asset_id"],
                            }
                        )
            selected["pages"][index] = projected
        except (DemoError, KeyError, ValueError, TypeError, OSError) as exc:
            selected.clear()
            selected.update(snapshot)
            decision = {
                "page_index": page["page_index"],
                "status": "ABSTAIN",
                "selected_provider": None,
                "reason": "PAGE_EVIDENCE_REJECTED",
                "error_type": type(exc).__name__,
            }
        decisions.append(decision)
    selected["metadata"]["geometry_arbitration"] = decisions
    return decisions


def run(
    source: Path, seal: Path, output_root: Path = JOBS, *, shared_structure: bool = True
) -> Path:
    """Freeze source evidence and apply only a unique supported provider to a fresh IR."""
    from .pipeline import finish

    before = inventory(source)
    sealed = read(seal)["artifacts"]
    if sealed != before:
        raise DemoError("SOURCE_SEAL_MISMATCH")
    original = read(source / "layout.auto.json")
    verify_source(source, original, before, sealed)
    if output_root.resolve().is_relative_to(source.resolve()):
        raise DemoError("OUTPUT_INSIDE_SOURCE")
    job = new_job(output_root)
    for asset_path in {a["path"] for a in original["assets"]} | {
        p["image_path"] for p in original["provenance"]["pages"].values()
    }:
        target = safe_path(job, asset_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(safe_path(source, asset_path), target)
        target.chmod(0o600)
    selected = copy.deepcopy(original)
    selected["document_id"] = job.name
    selected["metrics"]["model_call_count"] = 0
    requests = read(source / "request-manifest.json")["requests"]
    decisions = arbitrate_document(job, selected, source, requests)
    save(
        job / "request-manifest.json",
        {"authorized": False, "model_call_count": 0, "requests": [], "source_job_id": source.name},
    )
    save(job / "geometry-decisions.json", {"pages": decisions})
    save(job / "source-binding-ledger.json", selected["metadata"].get("source_binding_ledger", {}))
    if shared_structure:
        from .structure_processors.docvortex import DocVortexStructureProcessor

        processor = DocVortexStructureProcessor()
        shared = processor.process(selected)
        save(job / "shared-execution.json", processor.last_execution)
        finish(job, selected, structure_processor=processor, structure_candidate=shared)
    else:
        finish(job, selected)
    if inventory(source) != before:
        raise DemoError("SOURCE_CHANGED_DURING_REPLAY")
    save(
        job / "arbitration-receipt.json",
        {
            "source_seal_sha256": digest(seal),
            "source_files_unchanged": len(before),
            "model_calls": 0,
            "artifacts": inventory(job),
            "geometry_benefit": "NOT_VERIFIED",
        },
    )
    return job


def main() -> None:
    """Expose explicit sealed input and private output roots."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-job", type=Path, required=True)
    parser.add_argument("--source-seal", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=JOBS)
    parser.add_argument("--skip-shared-structure", action="store_true")
    args = parser.parse_args()
    print(
        run(
            args.source_job,
            args.source_seal,
            args.output_root,
            shared_structure=not args.skip_shared_structure,
        ).resolve()
    )


if __name__ == "__main__":
    main()
