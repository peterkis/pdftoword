"""Read-only, same-input A/B export into independent private jobs."""

from __future__ import annotations

import copy
import shutil
from pathlib import Path

from .common import JOBS, DemoError, Json, digest, new_job, read, safe_path, save, validate
from .pipeline import finish
from .renderers.base import DocxRenderer
from .renderers.legacy import LegacyRenderer
from .structure_processors.base import StructureProcessor


def inventory(root: Path) -> dict[str, str]:
    """Hash every file and reject symlinks, retaining the exact file set as evidence."""
    result = {}
    for path in sorted(root.rglob("*")):
        checked = safe_path(root, path.relative_to(root).as_posix())
        if checked.is_file():
            result[path.relative_to(root).as_posix()] = digest(checked)
    return result


def verify_source(source: Path, ir: Json, hashes: dict[str, str]) -> Json:
    """Check registered assets and stored response hashes, never hash a decoded substitute."""
    for asset in ir["assets"]:
        if hashes.get(asset["path"]) != asset["sha256"]:
            raise DemoError("ASSET_HASH_MISMATCH_OR_MISSING")
    manifest = read(source / "request-manifest.json") if (
        source / "request-manifest.json"
    ).exists() else {}
    verified = 0
    verified_raw = 0
    for request in manifest.get("requests", []):
        raw_name = request.get("raw_response_path")
        if raw_name:
            safe_path(source, raw_name)
            if hashes.get(raw_name) != request.get("response_sha256") or raw_name not in hashes:
                raise DemoError("RESPONSE_HASH_MISMATCH_OR_MISSING")
            verified_raw += 1
        if stored_hash := request.get("stored_response_sha256"):
            if raw_name:
                stored_name = str(Path(raw_name).with_suffix(".json"))
            elif request.get("region_id") and request.get("provider"):
                stored_name = f"response-{request['region_id']}-{request['provider']}.json"
            else:
                raise DemoError("STORED_RESPONSE_PATH_MISSING")
            safe_path(source, stored_name)
            if hashes.get(stored_name) != stored_hash:
                raise DemoError("STORED_RESPONSE_HASH_MISMATCH_OR_MISSING")
            verified += 1
    staged_inputs = [name for name in hashes if Path(name).parent == Path(".")
                     and Path(name).stem == "input"
                     and Path(name).suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"}]
    for name in staged_inputs:
        if hashes[name] != ir["source"]["sha256"]:
            raise DemoError("INPUT_HASH_MISMATCH")
    return {"historical_request_count": len(manifest.get("requests", [])),
            "verified_stored_responses": verified,
            "verified_raw_responses": verified_raw,
            "verified_staged_inputs": staged_inputs,
            "response_reexecution_count": 0,
            "provider_versions": ir.get("model_registry", {}),
            "unsealed_files": "snapshot_sha256_only_not_historical_authentication"}


def compare_renderers(
    source: Path, revision: str = "auto", output_root: Path = JOBS, *,
    renderer_a: DocxRenderer | None = None, renderer_b: DocxRenderer | None = None,
    structure_processor: StructureProcessor | None = None,
) -> Path:
    """Render the same saved IR twice without altering the original job or human revisions."""
    if revision not in {"auto", "reviewed"}:
        raise DemoError("INVALID_REVISION")
    source = source.absolute()
    if output_root.absolute().resolve().is_relative_to(source.resolve()):
        raise DemoError("OUTPUT_INSIDE_SOURCE")
    before = inventory(source)
    ir = read(safe_path(source, f"layout.{revision}.json"))
    validate(ir)
    if len(ir["pages"]) > 3:
        raise DemoError("PAGE_LIMIT_EXCEEDED")
    verification = verify_source(source, ir, before)
    comparison = new_job(output_root)
    evidence = comparison / "evidence"
    # Snapshot includes old outputs/overrides/responses, but they never enter the writer.
    evidence.mkdir(mode=0o700)
    for name, sha in before.items():
        target = safe_path(evidence, name)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(safe_path(source, name), target)
        target.chmod(0o600)
        if digest(target) != sha:
            raise DemoError("SOURCE_CHANGED_DURING_COPY")
    outputs = []
    for label, renderer in [("A", renderer_a or LegacyRenderer()),
                            ("B", renderer_b or LegacyRenderer())]:
        child = new_job(output_root)
        asset_paths = {a["path"] for a in ir["assets"]}
        asset_paths.update(p["image_path"] for p in ir["provenance"].get("pages", {}).values()
                           if "image_path" in p)
        for name in asset_paths:
            # Assets must not shadow job manifests, output or evidence files.
            if Path(name).parts[0] not in {"assets", "regions"}:
                raise DemoError("INVALID_ASSET_LOCATION")
            path = safe_path(evidence, name)
            if not path.is_file():
                raise DemoError("ASSET_MISSING")
            target = safe_path(child, name)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(path, target)
        candidate = copy.deepcopy(ir)
        candidate["metrics"]["model_call_count"] = 0
        save(child / "request-manifest.json", {
            "schema_version": "render-replay/1", "authorized": False,
            "model_call_count": 0, "requests": [],
            "source_ir_sha256": before[f"layout.{revision}.json"],
            "comparison_id": comparison.name, "revision": revision,
        })
        finish(child, candidate, renderer=renderer, structure_processor=structure_processor)
        outputs.append({"label": label, "job_id": child.name,
                        "renderer": {"name": renderer.name, "version": renderer.version},
                        "files": inventory(child)})
    if inventory(source) != before:
        raise DemoError("SOURCE_CHANGED_DURING_REPLAY")
    save(comparison / "comparison.json", {
        "schema_version": "render-comparison/1", "source_job_id": source.name,
        "source_revision": revision, "source_files": before, "source_unchanged": True,
        "source_ir_sha256": before[f"layout.{revision}.json"],
        "verification": verification, "outputs": outputs,
        "model_call_count": 0, "metadata_get_count": 0,
        "ir_reuse_count": 2, "response_reuse_count": 0,
    })
    return comparison
