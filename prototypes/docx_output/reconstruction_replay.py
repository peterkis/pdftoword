"""Four-group sealed reconstruction ablation, with no new model requests."""

from __future__ import annotations

import argparse
import copy
import shutil
from pathlib import Path

from .common import JOBS, DemoError, Json, digest, new_job, read, safe_path, save
from .pipeline import finish
from .planning.render_plan import RenderPlan
from .render_replay import inventory, verify_source
from .renderers.legacy import LegacyRenderer
from .structure_processors.base import StructureCandidate
from .structure_processors.docvortex import DocVortexStructureProcessor


def compare(source: Path, seal: Path, output_root: Path = JOBS) -> Path:
    """Freeze exact source files and produce a reviewable ablation without changing evidence."""
    before = inventory(source)
    sealed = read(seal)
    if sealed.get("artifacts", sealed.get("source_files")) != before:
        raise DemoError("SOURCE_SEAL_MISMATCH")
    if output_root.resolve().is_relative_to(source.resolve()):
        raise DemoError("OUTPUT_INSIDE_SOURCE")
    revision = "reviewed" if (source / "layout.reviewed.json").exists() else "auto"
    original = read(source / f"layout.{revision}.json")
    verify_source(source, original, before, before)
    root = new_job(output_root)
    outputs: list[Json] = []

    def create() -> tuple[Path, Json]:
        job = new_job(output_root)
        for asset in {a["path"] for a in original["assets"]} | {
            p["image_path"] for p in original["provenance"]["pages"].values()
        }:
            target = safe_path(job, asset)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(safe_path(source, asset), target)
            target.chmod(0o600)
        manifest = (
            read(source / "request-manifest.json")
            if (source / "request-manifest.json").exists()
            else {}
        )
        for entry in manifest.get("requests", []):
            name = f"response-{entry['region_id']}-{entry['provider']}.json"
            path = safe_path(source, name)
            if path.is_file():
                shutil.copyfile(path, job / name)
                (job / name).chmod(0o600)
        save(
            job / "request-manifest.json",
            {
                "authorized": False,
                "model_call_count": 0,
                "requests": manifest.get("requests", []),
                "source_job_id": source.name,
                "entries_are_sealed_evidence_only": True,
            },
        )
        ir = copy.deepcopy(original)
        ir["document_id"] = job.name
        ir["metrics"]["model_call_count"] = 0
        return job, ir

    # Actual shared finish seam used by CLI/API convert and execute-route.
    final, candidate = create()
    if revision == "auto":
        save(final / "route-plan.json", {"profile": "reconstruction-v2", "replay_only": True})
    else:
        candidate["metadata"].setdefault("reconstruction", {"profile": "reconstruction-v2"})
    finish(final, candidate, revision)
    fixed = read(final / f"layout.{revision}.json")
    frozen_loss = read(final / f"mapping-loss-report.{revision}.json")
    for kind in ("old_layout_old_renderer", "new_layout_same_renderer", "fixed_ir_flow"):
        job, baseline = create()
        value = baseline if kind == "old_layout_old_renderer" else copy.deepcopy(fixed)
        # Keep identical source IDs/content and exact IR for the fixed-renderer pair.
        processor = DocVortexStructureProcessor()
        frozen = StructureCandidate(value, copy.deepcopy(frozen_loss))
        if kind != "fixed_ir_flow":
            finish(
                job,
                value,
                revision,
                renderer=LegacyRenderer(),
                structure_candidate=frozen,
                render_plan=RenderPlan.from_ir(value),
                structure_processor=processor if kind == "new_layout_same_renderer" else None,
            )
        else:
            from .planning.flow import FlowPlan

            plan_data = read(final / f"render-plan.{revision}.json")
            plan = FlowPlan(value, plan_data["output_layout"])
            finish(
                job,
                value,
                revision,
                render_plan=plan,
                structure_candidate=frozen,
                structure_processor=processor,
            )
        outputs.append({"kind": kind, "job_id": job.name, "files": inventory(job)})
    outputs.append({"kind": "final_chain", "job_id": final.name, "files": inventory(final)})
    if inventory(source) != before:
        raise DemoError("SOURCE_CHANGED_DURING_REPLAY")
    save(
        root / "comparison.json",
        {
            "schema_version": "reconstruction-ablation/1",
            "source_job_id": source.name,
            "source_revision": revision,
            "source_seal_sha256": digest(seal),
            "source_files": before,
            "source_unchanged": True,
            "outputs": outputs,
            "groups": {
                "old_old": [outputs[0]["job_id"]],
                "new_same": [outputs[1]["job_id"]],
                "fixed_ir_renderers": [outputs[1]["job_id"], outputs[2]["job_id"]],
                "final": [final.name],
            },
            "model_calls": 0,
            "real_monkey_adoption": "NOT_VERIFIED",
            "word_acceptance": "NOT_RUN",
        },
    )
    return root


def main() -> int:
    """Explicit local sealed replay; never interprets execution as model authorization."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-job", type=Path, required=True)
    parser.add_argument("--source-seal", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=JOBS)
    args = parser.parse_args()
    try:
        result = compare(args.source_job, args.source_seal, args.output_root)
    except Exception as exc:
        code = str(exc) if isinstance(exc, DemoError) else type(exc).__name__
        if not all(c.isascii() and (c.isalnum() or c == "_") for c in code):
            code = type(exc).__name__
        print("RECONSTRUCTION_REPLAY_" + code)
        return 1
    print(result.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
