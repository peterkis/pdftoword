"""Shared offline route preparation and hash-bound, single-use region execution."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path

from PIL import Image

from .common import (
    DemoError,
    Json,
    digest,
    issue,
    new_job,
    read,
    safe_path,
    save,
    secure_tree,
)
from .raster_bridge import PP_PARAMETERS, PROMPTS, endpoint
from .region_router import prepare_page


def semantic_hash(value: Json) -> str:
    """Hash canonical private data without volatile JSON formatting."""
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def target_fingerprints() -> Json:
    """Bind configured destinations without sending probes or exposing URLs in UI."""
    return {
        p: semantic_hash(
            {
                "target": endpoint(p),
                "parameters": PP_PARAMETERS
                if p == "pp"
                else {"prompt": PROMPTS["ovis"], "max_tokens": 8192},
            }
        )
        for p in ("pp", "ovis")
    }


def deduplicate_asset_bytes(ir: Json) -> None:
    """Share identical bytes while keeping separate placement/source asset records."""
    paths: dict[str, str] = {}
    for asset in ir["assets"]:
        previous = paths.setdefault(asset["sha256"], asset["path"])
        asset["path"] = previous
    # Unreferenced files are left for existing explicit job cleanup; no user files are deleted.


def input_file(job: Path) -> Path:
    """Return the single staged input, rejecting ambiguous or linked files."""
    candidates = sorted(job.glob("input.*"))
    if len(candidates) != 1 or not candidates[0].is_file() or candidates[0].is_symlink():
        raise DemoError("ROUTE_INPUT_AMBIGUOUS")
    return candidates[0]


def prepare_routes(job: Path, ir: Json) -> Json:
    """Create an immutable local plan and source-preserving provisional DOCX content."""
    pages = []
    for p in ir["pages"]:
        index = p["page_index"]
        path = job / f"observation-{index}.json"
        if path.exists():
            observation = read(path)
        else:
            observation = {
                "geometry": {"width_pt": p["width_pt"], "height_pt": p["height_pt"]},
                "text_runs": [],
                "objects": [
                    {
                        "id": f"p{index}-raster",
                        "type": 3,
                        "bbox": [0, 0, p["width_pt"], p["height_pt"]],
                        "level": 0,
                    }
                ],
                "backend": {"status": "OK", "version": "not_applicable"},
            }
        decision = prepare_page(job, ir, p, observation)
        for region in decision["regions"]:
            if "asset_id" not in region:
                raise DemoError("REGION_GEOMETRY_UNRESOLVED")
            asset = next(a for a in ir["assets"] if a["id"] == region["asset_id"])
            with Image.open(safe_path(job, asset["path"])) as image:
                region["pixel_size"] = list(image.size)
            region["input_sha256"] = asset["sha256"]
        pages.append(decision)
    deduplicate_asset_bytes(ir)
    total = sum(r["request_budget"] for p in pages for r in p["regions"])
    plan: Json = {
        "schema_version": "route-plan/1",
        "job_id": job.name,
        "source_sha256": digest(input_file(job)),
        "selected_pages": [p["page_index"] for p in pages],
        "profile": "mixed-ovis-pp-v1",
        "pages": pages,
        "request_budget": total,
        "provider_aliases": ["pp", "ovis"] if total else [],
        "target_fingerprints": target_fingerprints() if total else {},
        "expires_at": time.time() + 86400,
        "status": "AWAITING_AUTHORIZATION" if total else "LOCAL_COMPLETE",
    }
    ir["metadata"]["auto_route"] = {
        "request_budget": total,
        "pending_regions": sum(r["route"] != "preserve" for p in pages for r in p["regions"]),
        "content_states": {str(p["page_index"]): p["content_state"] for p in pages},
    }
    save(job / "layout.prepared.json", ir)
    plan["prepared_sha256"] = digest(job / "layout.prepared.json")
    plan["plan_hash"] = semantic_hash(plan)
    save(job / "route-plan.json", plan)
    return plan


def validate_plan(job: Path, plan_hash: str, budget: int) -> Json:
    """Verify the original source, plan, crops, destinations, expiry, and approval bound."""
    if (job / "layout.reviewed.json").exists():
        raise DemoError("REVIEWED_SOURCE_REQUIRES_NEW_PLAN")
    plan = read(job / "route-plan.json")
    bare = {k: v for k, v in plan.items() if k != "plan_hash"}
    if semantic_hash(bare) != plan_hash or plan.get("plan_hash") != plan_hash:
        raise DemoError("ROUTE_PLAN_CHANGED")
    if time.time() > plan["expires_at"]:
        raise DemoError("ROUTE_PLAN_EXPIRED")
    if isinstance(budget, bool) or not isinstance(budget, int) or budget != plan["request_budget"]:
        raise DemoError("ROUTE_BUDGET_MISMATCH")
    if digest(input_file(job)) != plan["source_sha256"]:
        raise DemoError("ROUTE_SOURCE_CHANGED")
    if plan["request_budget"] and target_fingerprints() != plan["target_fingerprints"]:
        raise DemoError("ROUTE_TARGET_CHANGED")
    if digest(job / "layout.prepared.json") != plan["prepared_sha256"]:
        raise DemoError("ROUTE_PREPARED_CHANGED")
    ir = read(job / "layout.prepared.json")
    for page in plan["pages"]:
        for region in page["regions"]:
            asset = next(a for a in ir["assets"] if a["id"] == region["asset_id"])
            if digest(safe_path(job, asset["path"])) != region["input_sha256"]:
                raise DemoError("ROUTE_INPUT_CHANGED")
    return plan


def execute_routes(
    job: Path, plan_hash: str, budget: int, confirm_no_auth: bool, reuse_from: Path | None = None
) -> Path:
    """Execute once into a new job, never overwriting auto or human-reviewed output."""
    from .mixed_fusion import reconstruct_region
    from .pipeline import finish
    from .region_bridge import layout_purpose, request_region

    if not confirm_no_auth:
        raise DemoError("EXPLICIT_MODEL_AUTHORIZATION_REQUIRED")
    plan = validate_plan(job, plan_hash, budget)
    if reuse_from is not None:
        from .common import job_path

        reuse_from = job_path(reuse_from.name, job.parent)
        prior_plan = read(reuse_from / "route-plan.json")
        for key in ("source_sha256", "selected_pages", "profile", "target_fingerprints"):
            if prior_plan[key] != plan[key]:
                raise DemoError("REUSE_PLAN_MISMATCH")
    journal = job / "route-execution.json"
    # O_EXCL gives cross-thread/process admission; uncertain attempts are not retried.
    try:
        with journal.open("x") as out:
            out.write('{"status":"STARTED"}')
        journal.chmod(0o600)
    except FileExistsError as exc:
        raise DemoError("ROUTE_ALREADY_ATTEMPTED") from exc
    child = new_job(job.parent)
    for path in job.iterdir():
        if path.name == "assets":
            shutil.copytree(path, child / "assets", dirs_exist_ok=True)
        elif path.name.startswith(("input.", "observation-")):
            shutil.copyfile(path, child / path.name)
    ir = read(job / "layout.prepared.json")
    ir["metadata"]["parent_job_id"] = job.name
    ir["document_id"] = child.name
    manifest: Json = {
        "schema_version": "region-requests/1",
        "authorized": True,
        "approved_plan_hash": plan_hash,
        "budget": budget,
        "model_call_count": 0,
        "requests": [],
    }
    if reuse_from is not None:
        manifest["reuse_job_id"] = reuse_from.name
    save(child / "route-plan.json", plan)
    save(child / "request-manifest.json", manifest)
    save(journal, {"status": "STARTED", "child_job_id": child.name, "plan_hash": plan_hash})
    for p in plan["pages"]:
        for region in p["regions"]:
            if region["route"] == "preserve":
                continue
            if (job / "route-cancelled.json").exists():
                region["status"] = "CANCELLED"
                continue
            source = safe_path(
                child, next(a["path"] for a in ir["assets"] if a["id"] == region["asset_id"])
            )
            try:
                pp = request_region(child, source, region, "pp", manifest)
                purpose = layout_purpose(pp, region["pixel_size"])
                if purpose == "figure":
                    region["status"] = "PRESERVED_FIGURE"
                    continue
                if purpose not in {"text", "mixed"}:
                    raise DemoError("REGION_PURPOSE_REVIEW_REQUIRED")
                if (job / "route-cancelled.json").exists():
                    region["status"] = "CANCELLED"
                    continue
                # Never send known native text for OCR merely because it shares a crop.
                if region["native_blocks"] and region["reason"] not in (
                    "UNTRUSTED_NATIVE_RUN",
                    "INVISIBLE_TEXT_WITH_IMAGE",
                ):
                    raise DemoError("NATIVE_REGION_CONFLICT")
                ovis = request_region(child, source, region, "ovis", manifest)
                reconstruct_region(child, ir, region, {"pp": pp, "ovis": ovis}, manifest)
                region["status"] = "RECONSTRUCTED"
            except (DemoError, KeyError, IndexError, TypeError) as exc:
                region["status"] = (
                    str(exc) if isinstance(exc, DemoError) else "REGION_RECONSTRUCTION_FAILED"
                )
                issue(
                    ir,
                    "REGION_FALLBACK",
                    "局部处理失败，已保留该区域原图及其他原生内容。",
                    [region["region_id"]],
                    region["page_index"],
                )
            finally:
                ir["metrics"]["model_call_count"] = manifest["model_call_count"]
                save(child / "region-results.json", {"pages": plan["pages"]})
                save(child / "layout.partial.json", ir)
    save(child / "region-results.json", {"pages": plan["pages"]})
    ir["metadata"]["auto_route"]["request_budget"] = 0
    ir["metadata"]["auto_route"]["pending_regions"] = sum(
        r["status"] not in {"PRESERVED", "PRESERVED_FIGURE", "RECONSTRUCTED"}
        for p in plan["pages"]
        for r in p["regions"]
    )
    finish(child, ir)
    secure_tree(child)
    save(journal, {"status": "COMPLETE", "child_job_id": child.name, "plan_hash": plan_hash})
    return child
