"""Read-only source / Legacy / Flow comparison using existing sealed evidence."""

from __future__ import annotations

import argparse
import copy
import shutil
import sys
from pathlib import Path

from .common import JOBS, DemoError, Json, digest, new_job, read, safe_path, save
from .pipeline import finish
from .planning.flow import plan_flow
from .render_replay import inventory, verify_source
from .renderers.flow import FlowRenderer
from .structure_processors.base import StructureCandidate
from .structure_processors.docvortex import DocVortexStructureProcessor


def compare(
    source: Path, seal: Path, output_root: Path = JOBS, profile: Json | None = None
) -> Path:
    """Reuse one frozen shared result; write new baseline and Flow jobs without inference."""
    if output_root.resolve().is_relative_to(source.resolve()):
        raise DemoError("OUTPUT_INSIDE_SOURCE")
    before = inventory(source)
    manifest = read(seal)
    sealed = manifest.get("artifacts", manifest.get("source_files"))
    if sealed != before:
        raise DemoError("SOURCE_SEAL_MISMATCH")
    ir = read(source / "layout.auto.json")
    verification = verify_source(source, ir, before, sealed)
    shared = DocVortexStructureProcessor()
    frozen = shared.process(ir)
    selected = frozen.document
    selected["metrics"]["model_call_count"] = 0
    root = new_job(output_root)
    save(root / "shared-execution.json", shared.last_execution)
    outputs = []
    for kind in ["legacy", "flow"]:
        job = new_job(output_root)
        for asset_path in {a["path"] for a in selected["assets"]} | {
            p["image_path"] for p in selected["provenance"]["pages"].values()
        }:
            target = safe_path(job, asset_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(safe_path(source, asset_path), target)
            target.chmod(0o600)
        candidate = copy.deepcopy(selected)
        candidate["document_id"] = job.name
        save(
            job / "request-manifest.json",
            {
                "authorized": False,
                "model_call_count": 0,
                "requests": [],
                "source_job_id": source.name,
                "comparison_id": root.name,
            },
        )
        if kind == "flow":
            plan = plan_flow(candidate, profile)
            assert plan.document["pages"] == candidate["pages"]
            finish(
                job,
                plan.document,
                renderer=FlowRenderer(),
                render_plan=plan,
                structure_processor=shared,
                structure_candidate=StructureCandidate(plan.document, frozen.loss_report),
            )
        else:
            finish(
                job,
                candidate,
                structure_processor=shared,
                structure_candidate=StructureCandidate(candidate, frozen.loss_report),
            )
        outputs.append({"kind": kind, "job_id": job.name, "files": inventory(job)})
    if inventory(source) != before:
        raise DemoError("SOURCE_CHANGED_DURING_REPLAY")
    save(
        root / "comparison.json",
        {
            "schema_version": "flow-comparison/1",
            "source_job_id": source.name,
            "source_files": before,
            "source_unchanged": True,
            "source_seal_sha256": digest(seal),
            "verification": verification,
            "outputs": outputs,
            "model_calls": 0,
            "shared_stage": "LOCAL_PUBLIC_API",
            "product_acceptance": "NOT_RUN",
        },
    )
    return root


def main() -> int:
    """Select an explicit output profile without authorizing any model call."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-job", type=Path, required=True)
    parser.add_argument("--source-seal", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=JOBS)
    parser.add_argument("--body-size-pt", type=float)
    parser.add_argument("--east-asian-font")
    args = parser.parse_args()
    profile = {}
    if args.body_size_pt is not None:
        profile["body_size_pt"] = args.body_size_pt
    if args.east_asian_font:
        profile["east_asia_font"] = args.east_asian_font
    try:
        result = compare(args.source_job, args.source_seal, args.output_root, profile)
    except Exception as exc:
        code = (
            str(exc) if isinstance(exc, DemoError) else "FLOW_REPLAY_FAILED_" + type(exc).__name__
        )
        if not all(char.isascii() and (char.isalnum() or char == "_") for char in code):
            code = "FLOW_REPLAY_FAILED_" + type(exc).__name__
        print(code, file=sys.stderr)
        return 1
    print(result.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
