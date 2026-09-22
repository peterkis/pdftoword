"""Replan frozen Layout IR styles offline into a new job; never invoke an OCR provider."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .common import DemoError, Json, digest, new_job, read, safe_path, save, validate
from .output_profiles import output_settings, select_output_profile
from .pipeline import finish
from .planning.flow import plan_flow
from .render_replay import verify_source
from .renderers.flow import FlowRenderer
from .structure_processors.base import StructureCandidate
from .structure_processors.docvortex import DocVortexStructureProcessor


def export_style(
    source: Path,
    output_root: Path,
    profile: Json,
    source_sha256: str,
    *,
    output_profile: str = "legacy",
    revision: str = "auto",
) -> Path:
    """Verify the exact frozen IR and each declared asset before creating output."""
    source = source.resolve()
    if revision not in {"auto", "reviewed"}:
        raise DemoError("INVALID_REVISION")
    if output_root.resolve().is_relative_to(source):
        raise DemoError("OUTPUT_INSIDE_SOURCE")
    layout_path = safe_path(source, f"layout.{revision}.json")
    if digest(layout_path) != source_sha256:
        raise DemoError("STYLE_SOURCE_SEAL_MISMATCH")
    ir = read(layout_path)
    validate(ir)
    before = {str(p.relative_to(source)): digest(p) for p in source.rglob("*") if p.is_file()}
    for asset in ir["assets"]:
        if digest(safe_path(source, asset["path"])) != asset["sha256"]:
            raise DemoError("STYLE_ASSET_SEAL_MISMATCH")
    for page in ir["provenance"].get("pages", {}).values():
        if (
            "image_path" in page
            and page.get("image_sha256")
            and digest(safe_path(source, page["image_path"])) != page.get("image_sha256")
        ):
            raise DemoError("STYLE_SOURCE_IMAGE_SEAL_MISMATCH")
    verify_source(source, ir, before)
    select_output_profile(ir, output_profile)
    ir["metadata"]["parent_output"] = {
        "job_id": source.name,
        "revision": revision,
        "layout_sha256": source_sha256,
        "source_model_call_count": ir["metrics"].get("model_call_count", 0),
    }
    ir["metrics"]["model_call_count"] = 0
    plan = plan_flow(ir, {**(output_settings(ir) or {}), **profile})
    if plan.document["pages"] != ir["pages"] or plan.document["relations"] != ir["relations"]:
        raise DemoError("STYLE_SOURCE_MUTATED")
    job = new_job(output_root)
    plan.document["document_id"] = job.name
    paths = {a["path"] for a in ir["assets"]} | {
        p["image_path"] for p in ir["provenance"].get("pages", {}).values() if "image_path" in p
    }
    for name in paths:
        target = safe_path(job, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(safe_path(source, name), target)
    finish(
        job,
        plan.document,
        render_plan=plan,
        renderer=FlowRenderer(),
        structure_processor=DocVortexStructureProcessor(),
        structure_candidate=StructureCandidate(
            plan.document, {"status": "FROZEN_STYLE_ONLY", "losses": []}
        ),
    )
    if before != {str(p.relative_to(source)): digest(p) for p in source.rglob("*") if p.is_file()}:
        raise DemoError("STYLE_SOURCE_CHANGED_DURING_EXPORT")
    save(job / "style-profile.json", plan.document["metadata"]["style_profile"])
    save(
        job / "style-replay.json",
        {
            "source_layout_sha256": source_sha256,
            "source_files": before,
            "source_unchanged": True,
            "model_calls": 0,
            "structure_calls": 0,
            "profile": profile,
            "output_profile": output_profile,
            "source_revision": revision,
            "source_job_id": source.name,
            "output_docx_sha256": digest(job / "auto.docx"),
        },
    )
    return job


def main() -> int:
    """Expose a reproducible hash-bound style-only export command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-job", type=Path, required=True)
    parser.add_argument("--source-layout-sha256", required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    job = export_style(
        args.source_job, args.output_root, read(args.profile), args.source_layout_sha256
    )
    print(job)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
