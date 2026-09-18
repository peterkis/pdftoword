"""Explicit whole-page layout scope, separate from region content authorization."""

from __future__ import annotations

from pathlib import Path

from .common import ROOT, DemoError, Json, digest, issue, read, safe_path, save
from .geometry.candidate import attach, full_page
from .geometry.monkey_adapter import adapt
from .raster_bridge import endpoint


def profile_settings(profile: str) -> Json:
    """Load the opt-in profile without consulting any model service."""
    if profile == "legacy_ovis_pp":
        return {
            "profile": profile,
            "content_provider": "ovis",
            "region_layout_provider": "pp",
            "page_layout_provider": None,
            "implicit_retries": 0,
        }
    if profile != "reconstruction-v2":
        raise DemoError("UNKNOWN_AUTO_PROFILE")
    settings = read(ROOT / "config/profiles/reconstruction-v2.json")
    expected = {
        "profile": profile,
        "content_provider": "ovis",
        "region_layout_provider": "pp",
        "page_layout_provider": "monkey",
        "page_layout_max_requests": 1,
        "implicit_retries": 0,
        "provider_revision": None,
    }
    if settings != expected:
        raise DemoError("UNSUPPORTED_AUTO_PROFILE_SETTINGS")
    return settings


def prepare_layout(job: Path, ir: Json, decisions: list[Json], profile: str) -> list[Json]:
    """Offer at most one complete visible-page send for nontrivial pages."""
    settings = profile_settings(profile)
    if settings["page_layout_provider"] is None:
        return []
    tasks = []
    for decision in decisions:
        if decision["content_state"] == "blank":
            continue
        # Valid simple native text never needs a model. Existing uncertainty,
        # raster content or mixed objects are evidence for a reviewable layout plan.
        if (
            decision["page_type"] == "native"
            and not decision["reason_codes"]
            and not decision["regions"]
        ):
            continue
        page = next(p for p in ir["pages"] if p["page_index"] == decision["page_index"])
        info = ir["provenance"]["pages"][str(page["page_index"])]
        source = safe_path(job, info["image_path"])
        target, model = endpoint("monkey")
        tasks.append(
            {
                "region_id": f"p{page['page_index']}-page-layout",
                "page_index": page["page_index"],
                "provider": "monkey",
                "task_type": "page_layout",
                "scope": "whole_visible_page",
                "image_path": info["image_path"],
                "input_sha256": digest(source),
                "pixel_size": info["pixel_size"],
                "bbox": [0, 0, page["width_pt"], page["height_pt"]],
                "reason": "COMPLEX_OR_RASTER_PAGE_LAYOUT",
                "target": target,
                "model": model,
                "provider_revision": None,
                "request_budget": 1,
                "status": "AWAITING_AUTHORIZATION",
            }
        )
    return tasks


def execute_layout(parent: Path, child: Path, ir: Json, tasks: list[Json], manifest: Json) -> None:
    """Use the shared request ledger and add only unselected geometry evidence."""
    from .region_bridge import request_region
    from .route_plan import semantic_hash

    for task in tasks:
        page = next(p for p in ir["pages"] if p["page_index"] == task["page_index"])
        before = semantic_hash({"blocks": page["blocks"], "reading_order": page["reading_order"]})
        if (parent / "route-cancelled.json").exists():
            task["status"] = "CANCELLED"
            manifest["requests"].append(
                {
                    "provider": "monkey",
                    "region_id": task["region_id"],
                    "page_index": task["page_index"],
                    "task_type": "page_layout",
                    "status": "CANCELLED",
                    "http_attempted": False,
                    "input_sha256": task["input_sha256"],
                }
            )
            save(child / "request-manifest.json", manifest)
            continue
        try:
            body = request_region(
                child, safe_path(child, task["image_path"]), task, "monkey", manifest
            )
            entry = manifest["requests"][-1]
            info = ir["provenance"]["pages"][str(page["page_index"])]
            output = adapt(
                body,
                page["page_index"],
                full_page(page, info),
                {
                    "request_id": entry["request_id"],
                    "model_fingerprint": entry.get("target_fingerprint"),
                    "prompt_fingerprint": entry.get("prompt_sha256"),
                    "response_sha256": entry["stored_response_sha256"],
                    "provider_revision": None,
                },
            )
            attach(page, output)
            task.update(
                status="CANDIDATES_AVAILABLE"
                if output["geometry_candidates"]
                else "NO_VALID_CANDIDATES",
                candidate_count=len(output["geometry_candidates"]),
                rejection_count=len(output["rejections"]),
                selected_geometry_id=None,
            )
            entry["geometry_status"] = task["status"]
            if not output["geometry_candidates"]:
                entry["status"] = "NO_VALID_GEOMETRY"
                issue(
                    ir,
                    "PAGE_LAYOUT_UNAVAILABLE",
                    "整页布局未得到有效候选，保留正文和原有几何。",
                    [],
                    page["page_index"],
                )
            if output["rejections"]:
                entry["geometry_rejection_count"] = len(output["rejections"])
        except (DemoError, KeyError, ValueError, TypeError) as exc:
            task["status"] = str(exc) if isinstance(exc, DemoError) else "LAYOUT_CANDIDATE_REJECTED"
            if not any(
                r["region_id"] == task["region_id"] and r["provider"] == "monkey"
                for r in manifest["requests"]
            ):
                manifest["requests"].append(
                    {
                        "provider": "monkey",
                        "region_id": task["region_id"],
                        "page_index": task["page_index"],
                        "task_type": "page_layout",
                        "status": task["status"],
                        "http_attempted": False,
                        "input_sha256": task["input_sha256"],
                    }
                )
            issue(
                ir,
                "PAGE_LAYOUT_UNAVAILABLE",
                "整页布局未得到有效候选，保留正文和原有几何。",
                [],
                page["page_index"],
            )
        finally:
            after = semantic_hash(
                {"blocks": page["blocks"], "reading_order": page["reading_order"]}
            )
            if after != before:
                raise DemoError("LAYOUT_CHANGED_CONTENT")
            task["content_hash_before"] = before
            task["content_hash_after"] = after
            ir["metrics"]["model_call_count"] = manifest["model_call_count"]
            save(child / "request-manifest.json", manifest)
            save(child / "layout-results.json", {"tasks": tasks})
