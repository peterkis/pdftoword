"""Shared reconstruction-v2 export seam; no network or implicit model requests."""

from __future__ import annotations

import copy
from pathlib import Path

from .common import DemoError, Json, issue, read, save
from .geometry_arbitration import arbitrate_document
from .planning.flow import FlowPlan, plan_flow
from .planning.paragraphs import build_native_paragraphs, verify_native_transition
from .structure_processors.base import StructureCandidate
from .structure_processors.bridge import json_hash
from .structure_processors.docvortex import DocVortexStructureProcessor


def enabled(job: Path, ir: Json) -> bool:
    """Resolve explicit route profile or persisted export profile for reviewed output."""
    if ir["metadata"].get("reconstruction", {}).get("profile") == "reconstruction-v2":
        return True
    route = job / "route-plan.json"
    return route.is_file() and read(route).get("profile") == "reconstruction-v2"


def prepare(
    job: Path, ir: Json, revision: str
) -> tuple[FlowPlan, StructureCandidate, DocVortexStructureProcessor, Json]:
    """Arbitrate once, process shared structure once, then plan without an IR round trip."""
    selected = copy.deepcopy(ir)
    prior = selected["metadata"].get("reconstruction", {})
    processor = DocVortexStructureProcessor()
    execution: Json = {"model_calls": 0, "revision": revision}
    if prior:
        # Reviewed revisions may deliberately change content. Never feed finalized Middle
        # or reviewed/locked geometry back into automatic selection or shared merging.
        if revision == "auto" and prior.get("source_state_sha256") != source_state(selected):
            raise DemoError("RECONSTRUCTION_STAGE_STALE")
        candidate = StructureCandidate(selected, {"status": "REUSED_FINALIZED", "losses": []})
        execution["structure_status"] = "REUSED_FINALIZED"
    else:
        manifest = (
            read(job / "request-manifest.json") if (job / "request-manifest.json").is_file() else {}
        )
        decisions = arbitrate_document(job, selected, job, manifest.get("requests", []))
        execution["geometry_pages"] = decisions
        native_source = selected
        selected = build_native_paragraphs(native_source)
        execution["native_transition"] = verify_native_transition(native_source, selected)
        save(
            job / f"native-paragraph-ledger.{revision}.json",
            selected["metadata"]["native_paragraphs"],
        )
        try:
            candidate = processor.process(selected)
            execution["structure_status"] = (
                "REUSED_FINALIZED"
                if candidate.loss_report.get("status") == "ALREADY_FINALIZED"
                else "EXECUTED_PUBLIC_API"
            )
            execution["public_execution"] = processor.last_execution
        except (DemoError, ValueError, KeyError, TypeError, OSError) as exc:
            issue(
                selected,
                "SHARED_STRUCTURE_UNAVAILABLE",
                "共享结构未采用，保留最后可用来源结构。",
                [],
                selected["pages"][0]["page_index"],
            )
            candidate = StructureCandidate(
                selected,
                {"status": "FALLBACK", "losses": [{"code": "SHARED_STRUCTURE_UNAVAILABLE"}]},
            )
            execution.update(structure_status="FALLBACK", error_type=type(exc).__name__)
    selected = candidate.document
    selected["metadata"]["reconstruction"] = {
        "profile": "reconstruction-v2",
        "version": "1",
        "structure_status": execution["structure_status"],
        "structure_processor": {"name": processor.name, "version": processor.version},
        "renderer": {"name": "flow", "version": "1"},
        "source_state_sha256": source_state(selected),
    }
    plan = plan_flow(selected)
    candidate.document = plan.document
    save(job / f"reconstruction-execution.{revision}.json", execution)
    save(
        job / f"source-binding-ledger.{revision}.json",
        selected["metadata"].get("source_binding_ledger", {}),
    )
    return plan, candidate, processor, execution


def source_state(ir: Json) -> str:
    """Hash content, measured geometry and relations, independently of output planning."""
    return json_hash({key: ir[key] for key in ("pages", "relations", "assets")})


def page_status(ir: Json, renderer: str) -> list[Json]:
    """Expose selection and execution separately from visual or human acceptance."""
    decisions = {d["page_index"]: d for d in ir["metadata"].get("geometry_arbitration", [])}
    result = []
    for page in ir["pages"]:
        d = decisions.get(page["page_index"], {})
        result.append(
            {
                "page_index": page["page_index"],
                "selected_geometry_provider": d.get("selected_provider"),
                "layout_status": d.get("status", "NOT_RUN"),
                "retained_geometry_sources": sorted({b["geometry_source"] for b in page["blocks"]}),
                "renderer": renderer,
                "renderer_fallback": ir["metadata"]
                .get("reconstruction", {})
                .get("renderer_fallback"),
                "issue_codes": sorted(
                    {
                        i["type"]
                        for i in ir["issues"]
                        if i.get("page_index") in (None, page["page_index"])
                    }
                ),
                "human_acceptance": "PENDING",
            }
        )
    return result
