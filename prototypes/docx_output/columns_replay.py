"""Hash-sealed offline column reconstruction; no model requests or source writes."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .common import DemoError, digest, new_job, read, safe_path, save
from .pipeline import finish
from .planning.columns import select_columns, verify_selected_order
from .planning.flow import plan_flow
from .reconstruction import source_state
from .render_replay import inventory, verify_source
from .renderers.flow import FlowRenderer
from .structure_processors.base import StructureCandidate
from .structure_processors.docvortex import DocVortexStructureProcessor


def export_columns(source: Path, seal: Path, output_root: Path) -> Path:
    """Verify a complete existing file seal, select order, call public structure, render anew."""
    if output_root.resolve().is_relative_to(source.resolve()):
        raise DemoError("OUTPUT_INSIDE_SOURCE")
    before = inventory(source)
    sealed = read(seal).get("source_files")
    if sealed != before:
        raise DemoError("SOURCE_SEAL_MISMATCH")
    original = read(safe_path(source, "layout.auto.json"))
    verification = verify_source(source, original, before, sealed)
    selected = select_columns(original)
    processor = DocVortexStructureProcessor()
    candidate = processor.process(selected)
    verify_selected_order(selected, candidate.document)
    selected = candidate.document
    if selected["metadata"].get("reconstruction"):
        selected["metadata"]["reconstruction"]["source_state_sha256"] = source_state(selected)
        selected["metadata"]["reconstruction"]["structure_status"] = "EXECUTED_PUBLIC_API"
    plan = plan_flow(selected)
    job = new_job(output_root)
    for name in {a["path"] for a in selected["assets"]} | {
        p["image_path"] for p in selected["provenance"].get("pages", {}).values()
    }:
        target = safe_path(job, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(safe_path(source, name), target)
    finish(
        job,
        plan.document,
        renderer=FlowRenderer(),
        structure_processor=processor,
        structure_candidate=StructureCandidate(plan.document, candidate.loss_report),
        render_plan=plan,
    )
    save(job / "column-layout.json", selected["metadata"]["column_layout"])
    save(job / "public-execution.json", processor.last_execution)
    if inventory(source) != before:
        raise DemoError("SOURCE_CHANGED_DURING_COLUMN_REPLAY")
    save(
        job / "column-replay.json",
        {
            "source_files": before,
            "source_unchanged": True,
            "source_seal_sha256": digest(seal),
            "verification": verification,
            "model_calls": 0,
            "public_order_preserved": True,
        },
    )
    return job


def main() -> int:
    """Run an explicit bounded offline replay against a caller-selected sealed job."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-job", type=Path, required=True)
    parser.add_argument("--source-seal", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        job = export_columns(args.source_job, args.source_seal, args.output_root)
    except Exception as exc:
        code = (
            str(exc)
            if isinstance(exc, DemoError)
            else "COLUMN_REPLAY_FAILED_" + type(exc).__name__.upper()
        )
        if not code or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in code):
            code = "COLUMN_REPLAY_FAILED"
        print(code, file=sys.stderr)
        return 1
    print(job)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
