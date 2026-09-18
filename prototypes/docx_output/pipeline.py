"""Shared CLI/UI orchestration, with immutable automatic output."""

from __future__ import annotations

import copy
import re
import shutil
from pathlib import Path

from . import VERSION
from .common import (
    JOBS,
    DemoError,
    Json,
    area,
    block,
    crop,
    digest,
    finish_preview,
    image_size,
    layout,
    new_job,
    page,
    prune_preview_assets,
    read,
    save,
    secure_tree,
    union_area,
    validate_input,
)
from .implementation import implementation_identity
from .planning.render_plan import PLAN_VERSION, RenderPlan
from .renderers.base import DocxRenderer
from .renderers.legacy import LegacyRenderer
from .replay import DEFAULT_RUN, load
from .structure import image_content, recover, recover_monkey
from .structure_processors.base import StructureCandidate, StructureProcessor
from .structure_processors.legacy import LegacyStructureProcessor


def source_image(job: Path, ir: Json, source: Path, index: int = 0) -> Json:
    """Copy source raster and declare virtual paper dimensions explicitly."""
    w, h = image_size(source)
    target = job / "assets" / f"source-{index}{source.suffix.lower()}"
    shutil.copyfile(source, target)
    target.chmod(0o600)
    scale = 595.28 / w
    p = page(index, 595.28, h * scale, "scanned")
    ir["provenance"].setdefault("pages", {})[str(index)] = {
        "image_path": str(target.relative_to(job)),
        "image_sha256": digest(target),
        "pixel_size": [w, h],
        "pixel_to_point": [scale, scale],
        "point_to_pixel": [1 / scale, 1 / scale],
        "size_basis": "virtual_width_595.28pt_not_DPI",
        "source_page_1based": index + 1,
    }
    ir["pages"].append(p)
    return p


def finish(
    job: Path, ir: Json, revision: str = "auto", *,
    renderer: DocxRenderer | None = None,
    structure_processor: StructureProcessor | None = None,
    structure_candidate: StructureCandidate | None = None,
) -> Json:
    """Export, audit and persist each revision without inference."""
    if revision not in {"auto", "reviewed"}:
        raise DemoError("INVALID_REVISION")
    if revision == "auto" and (job / "auto.docx").exists():
        raise DemoError("AUTO_IMMUTABLE")
    save(job / "state.json", {"state": "导出"})
    renderer = renderer or LegacyRenderer()
    structure_processor = structure_processor or LegacyStructureProcessor()
    candidate = (copy.deepcopy(structure_candidate) if structure_candidate is not None
                 else structure_processor.process(copy.deepcopy(ir)))
    ir = candidate.document
    plan = RenderPlan.from_ir(ir)
    stats = renderer.render(job, plan, revision)
    save(job / f"render-plan.{revision}.json", plan.as_dict())
    save(job / f"structure-candidate.{revision}.json", candidate.document)
    save(job / f"mapping-loss-report.{revision}.json", candidate.loss_report)
    save(job / f"render-manifest.{revision}.json", {
        "renderer": {"name": renderer.name, "version": renderer.version,
                     "implementation": implementation_identity(renderer, "render")},
        "structure_processor": {"name": structure_processor.name,
                                "version": structure_processor.version,
                                "implementation": implementation_identity(
                                    structure_processor, "process")},
        "ir_version": ir["schema_version"], "plan_version": PLAN_VERSION,
        "effective_renderer": stats.get("effective_renderer", renderer.name),
        "providers": ir.get("model_registry", {}), "model_call_count": 0,
        "provider_revision_if_absent": "unknown",
        "implementation_sha256": {
            name: digest(Path(__file__).parent / name) for name in (
                "pipeline.py", "writer.py", "planning/render_plan.py",
                "renderers/base.py", "renderers/legacy.py",
                "structure_processors/base.py", "structure_processors/legacy.py",
            )
        },
    })
    fallback_boxes: dict[int, list[list[float]]] = {}
    referenced = set()
    figure_assets = set()
    for p in ir["pages"]:
        for b in p["blocks"]:
            if b["content"]["kind"] == "image":
                aid = b["content"]["asset_id"]
                referenced.add(aid)
                if b["type"] == "figure":
                    figure_assets.add(aid)
                else:
                    fallback_boxes.setdefault(p["page_index"], []).append(b["bbox"])
    for pieces in ir["metadata"].get("inline_parts", {}).values():
        for piece in pieces:
            if "asset_id" in piece and "omml" not in piece:
                referenced.add(piece["asset_id"])
    for a in ir["assets"]:
        if a["id"] in referenced and a["type"] == "formula_image":
            fallback_boxes.setdefault(a["source_page_index"], []).append(a["source_bbox"])
    for asset in ir["assets"]:
        if asset["id"] in stats.get("rendered_fallback_asset_ids", []):
            fallback_boxes.setdefault(asset["source_page_index"], []).append(asset["source_bbox"])
    total = sum(p["width_pt"] * p["height_pt"] for p in ir["pages"])
    fallback = 0.0
    for p in ir["pages"]:
        bounded = [
            [max(0, b[0]), max(0, b[1]), min(p["width_pt"], b[2]), min(p["height_pt"], b[3])]
            for b in fallback_boxes.get(p["page_index"], [])
        ]
        fallback += union_area([b for b in bounded if area(b)])
    auxiliary_ids = {r["from"] for r in ir["relations"] if r["type"] in {"label_of", "caption_of"}}
    editable_formula_ids = set(stats.get("editable_formula_block_ids", []))
    page_editable_content = {
        str(p["page_index"]): any(
            b["id"] not in auxiliary_ids
            and (
                (b["content"]["kind"] == "formula" and b["id"] in editable_formula_ids)
                or (
                    b["content"]["kind"] == "text"
                    and b["type"] in {
                        "paragraph", "heading", "question", "option", "formula", "table",
                        "major_question", "subquestion", "text_line", "text_span"
                    }
                    and not re.fullmatch(
                        r"[A-D][.．、]?", b["content"].get("plain_text", "").strip()
                    )
                    and bool(b["content"].get("plain_text", "").strip())
                )
            )
            for b in p["blocks"]
        )
        for p in ir["pages"]
    }
    auto_states = ir["metadata"].get("auto_route", {}).get("content_states", {})
    for key, state in auto_states.items():
        if state == "blank":
            page_editable_content[key] = True
    qa = dict(
        execution_status=(
            "COMPLETE"
            if all(page_editable_content.values())
            and (stats["has_editable_runs"] or bool(auto_states))
            else "DEMO_OUTPUT_INSUFFICIENT"
        ),
        page_editable_content=page_editable_content,
        content_review_status="REVIEW_REQUIRED",
        layout_validation=ir["metadata"].get("layout_validation", {"status": "NOT_APPLICABLE"}),
        structure_review_status="REVIEW_REQUIRED",
        render_status="DOCX_VISUAL_REVIEW_PENDING",
        visual_review_status="PENDING",
        model_call_count=ir["metrics"].get("model_call_count", 0),
        unique_figure_asset_count=len(figure_assets),
        fallback_area_ratio=fallback / total,
        fallback_area_denominator="sum_selected_page_area_pt2; rectangle_union_per_page",
        manual_override_count=ir["metrics"].get("manual_override_count", 0),
        unresolved_issue_count=sum(i["status"] == "open" for i in ir["issues"]),
        **stats,
    )
    if ir["metadata"].get("auto_route", {}).get("pending_regions", 0):
        qa["execution_status"] = "PARTIAL"
    save(job / f"layout.{revision}.json", ir)
    save(job / ("qa.json" if revision == "auto" else "qa.reviewed.json"), qa)
    save(
        job / ("issues.json" if revision == "auto" else "issues.reviewed.json"),
        {"issues": ir["issues"]},
    )
    from .review import write_preview

    write_preview(job, ir, revision)
    save(job / "state.json", {"state": "待复核", "execution_status": qa["execution_status"]})
    secure_tree(job)
    return qa


def reconstruct(
    job: Path, ir: Json, p: Json, responses: Json, manifest: Json, content_provider: str
) -> None:
    """Use one content/geometry reconstruction path for replay and authorized uploads."""
    from .common import issue

    primary = "ovis" if content_provider in {"ovis", "ovis-pp"} else "pp"
    if primary not in responses:
        bounds = [0.0, 0.0, p["width_pt"], p["height_pt"]]
        bid = f"p{p['page_index']}-missing-primary"
        aid = crop(job, ir, p, bounds, bid)
        b = block(bid, p["page_index"], bounds, "", "inferred")
        b.update(content=image_content(aid), render_policy="preserve_image")
        p["blocks"].append(b)
        p["reading_order"].append(bid)
        p["routing_decision"] = "PRIMARY_CONTENT_MISSING_SOURCE_FALLBACK"
        issue(
            ir,
            "PRIMARY_CONTENT_MISSING",
            "主识别未完成；保留源页，不替换内容来源。",
            [bid],
            p["page_index"],
        )
        return
    if primary == "pp":
        before = copy.deepcopy(ir)
        before_files = set((job / "assets").glob("*.png"))
        try:
            recover(job, ir, p, responses, manifest)
        except (ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
            index = p["page_index"]
            ir.clear()
            ir.update(before)
            restored = next(pg for pg in ir["pages"] if pg["page_index"] == index)
            p.clear()
            p.update(restored)
            ir["pages"] = [p if pg["page_index"] == index else pg for pg in ir["pages"]]
            prune_preview_assets(job, set((job / "assets").glob("*.png")) - before_files)
            bounds = [0.0, 0.0, p["width_pt"], p["height_pt"]]
            bid = f"p{index}-pp-recovery-fallback"
            aid = crop(job, ir, p, bounds, bid)
            b = block(bid, index, bounds, "", "inferred")
            b.update(content=image_content(aid), render_policy="preserve_image")
            p["blocks"].append(b)
            p["reading_order"].append(bid)
            p["routing_decision"] = "PP_RECONSTRUCTION_FALLBACK"
            ir["provenance"].setdefault("rejected_pp_response", {})[str(index)] = responses["pp"]
            issue(
                ir,
                "PP_RECONSTRUCTION_FALLBACK",
                "PP内部结果无法安全重建，保留响应及源页图片待审校：" + type(exc).__name__,
                [bid],
                index,
            )
        return
    from .ovis_replay import recover_ovis
    from .pp_layout import apply_pp_layout

    def request_id(provider: str) -> str:
        return next(
            (
                r["request_id"]
                for r in manifest["requests"]
                if r.get("provider") == provider
                and r.get("page_index", p["page_index"]) == p["page_index"]
            ),
            "unavailable",
        )

    recover_ovis(job, ir, p, responses["ovis"], request_id("ovis"))
    if content_provider == "ovis-pp":
        apply_pp_layout(job, ir, p, responses.get("pp", {}), request_id("pp"))
    recover_monkey(ir, p, responses)


def replay(
    run: Path = DEFAULT_RUN,
    variant: str = "jpg",
    repeat: int = 1,
    output_root: Path = JOBS,
    content_provider: str = "ovis-pp",
) -> Path:
    """Produce a real Word document from sealed historical responses with zero HTTP."""
    if content_provider not in {"pp", "ovis", "ovis-pp"}:
        raise DemoError("INVALID_CONTENT_PROVIDER")
    providers = (
        ("ovis",)
        if content_provider == "ovis"
        else ("ovis", "pp")
        if content_provider == "ovis-pp"
        else ("pp", "ovis", "monkey")
    )
    source, responses, provenance = load(run, variant, repeat, providers)
    provenance["content_provider"] = content_provider
    job = new_job(output_root)
    try:
        validate_input(source)
        ir = layout(job, source, 1)
        ir["provenance"]["replay"] = provenance
        ir["metrics"]["model_call_count"] = 0
        save(
            job / "input-manifest.json",
            {**ir["source"], "mode": "replay", "source_run_id": provenance["source_run_id"]},
        )
        save(job / "request-manifest.json", {**provenance, "demo_version": VERSION})
        p = source_image(job, ir, source)
        save(job / "state.json", {"state": "结构恢复"})
        reconstruct(job, ir, p, responses, provenance, content_provider)
        finish(job, ir)
    except Exception as exc:
        save(
            job / "state.json",
            {
                "state": "失败",
                "code": str(exc) if isinstance(exc, DemoError) else type(exc).__name__,
            },
        )
        raise
    return job


def export(job: Path, revision: str = "reviewed") -> Path:
    """Re-export persisted human overrides; no network path exists here."""
    if revision != "reviewed":
        raise DemoError("AUTO_IMMUTABLE")
    from .review import apply_overrides

    previous = read(job / "layout.reviewed.json") if (job / "layout.reviewed.json").exists() else {}
    old_assets = {job / a["path"] for a in previous.get("assets", [])}
    ir = apply_overrides(job, read(job / "layout.auto.json"), read(job / "overrides.json"))
    finish(job, ir, revision)
    finish_preview(job)
    prune_preview_assets(job, old_assets)
    return job / "reviewed.docx"


def convert(
    source: Path,
    selection: str | None = None,
    mode: str = "native",
    output_root: Path = JOBS,
    allow_model_calls: bool = False,
    confirm_no_auth: bool = False,
    ovis: bool = False,
    monkey: bool = False,
    confirm_scan: bool = False,
    synthetic: bool = False,
    content_provider: str = "ovis-pp",
) -> Path:
    """Convert authorized local input using a finite native or explicit live route."""
    validate_input(source)
    if content_provider not in {"ovis", "ovis-pp", "pp"}:
        raise DemoError("INVALID_CONTENT_PROVIDER")
    if mode == "auto" and (content_provider != "ovis-pp" or ovis or monkey):
        raise DemoError("AUTO_PROFILE_OVIS_PP_REQUIRED")
    if mode not in {"native", "raster", "auto"}:
        raise DemoError("INVALID_MODE")
    if mode == "raster" and not (allow_model_calls and confirm_no_auth):
        raise DemoError("EXPLICIT_MODEL_AUTHORIZATION_REQUIRED")
    if mode == "native" and source.suffix.lower() != ".pdf":
        raise DemoError("NATIVE_REQUIRES_PDF")
    if mode == "raster" and source.suffix.lower() == ".pdf" and not confirm_scan:
        raise DemoError("SCAN_CONFIRMATION_REQUIRED")
    job = new_job(output_root)
    ir = layout(job, source, 1)
    ir["metrics"]["model_call_count"] = 0
    manifest: Json = {
        "requests": [],
        "model_call_count": 0,
        "mode": mode,
        "content_provider": content_provider,
        "demo_version": VERSION,
        "authorized": allow_model_calls,
        "confirm_no_auth": confirm_no_auth,
        "confirm_scan": confirm_scan,
    }
    save(job / "request-manifest.json", manifest)
    target = job / ("input" + source.suffix.lower())
    shutil.copyfile(source, target)
    target.chmod(0o600)
    try:
        save(job / "state.json", {"state": "提取/识别"})
        if target.suffix.lower() == ".pdf":
            from .native_pdf import extract

            extract(job, ir, target, selection, raster_only=mode == "raster")
        else:
            if selection not in {None, "1"}:
                raise DemoError("IMAGE_HAS_ONE_PAGE")
            source_image(job, ir, target)
        save(
            job / "input-manifest.json",
            {**ir["source"], "mode": mode, "synthetic": synthetic, "pages_1based": selection},
        )
        if mode == "raster":
            from .raster_bridge import recognize

            for page_offset in range(len(ir["pages"])):
                p = ir["pages"][page_offset]
                responses = recognize(job, ir, p, manifest, ovis, monkey, content_provider)
                save(job / "state.json", {"state": "结构恢复"})
                reconstruct(job, ir, p, responses, manifest, content_provider)
        if mode == "auto":
            from .route_plan import prepare_routes

            prepare_routes(job, ir)
        finish(job, ir)
    except Exception as exc:
        save(job / "layout.partial.json", ir)
        save(
            job / "state.json",
            {
                "state": "失败",
                "code": str(exc) if isinstance(exc, DemoError) else type(exc).__name__,
            },
        )
        secure_tree(job)
        raise
    return job
