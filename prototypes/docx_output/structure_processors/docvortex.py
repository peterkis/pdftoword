"""Public shared structure proposals gated by explicit source and content conservation."""

from __future__ import annotations

import copy
from typing import Any

from ..common import Json, issue, relation, validate
from ..docvortex_runtime import call_worker
from .base import StructureCandidate
from .bridge import bridge, inline_text, json_hash


def leaves(block: Json) -> list[Json]:
    """Traverse structural children only; inline spans are content atoms, not blocks."""
    children = block.get("content")
    if isinstance(children, list) and any(isinstance(c, dict) and "index" in c for c in children):
        return [leaf for child in children for leaf in leaves(child)]
    return [block]


def locked(block: Json) -> bool:
    """Human edits and any explicit lock suppress new shared structural choices."""
    return (
        block.get("geometry_source") == "manual_correction"
        or block.get("source_type") == "manual_correction"
        or any("lock" in flag for flag in block.get("flags", []))
    )


def finalized_hash(ir: Json) -> str:
    """Bind a stage marker to the whole IR except its own audit record."""
    value = copy.deepcopy(ir)
    value["metadata"].pop("docvortex_structure", None)
    return json_hash(value)


class DocVortexStructureProcessor:
    """Keep original content/geometry; adopt only independently source-bound structure hints."""

    name = "docvortex-public"
    version = "0.4.9/p2w-1"

    def __init__(self) -> None:
        """Retain actual invocation artifacts for the private POC evidence publisher."""
        self.last_execution: Json = {}

    def process(self, selected: Json) -> StructureCandidate:
        """Call real ModelJson→MiddleJson once, retaining ambiguity rather than guessing IDs."""
        from .conservation import continuation_rejection, verify_shared

        validate(selected)
        stage = selected["metadata"].get("docvortex_structure", {})
        if isinstance(stage, dict) and stage.get("finalized_ir_sha256") == finalized_hash(selected):
            return StructureCandidate(
                copy.deepcopy(selected), {"status": "ALREADY_FINALIZED", "losses": []}
            )
        value = bridge(selected)
        result = call_worker({"action": "postprocess", "model": value.model})
        middle = result["middle"]
        candidate = copy.deepcopy(selected)
        prior_links = [
            r
            for r in candidate["relations"]
            if r["type"] == "continuation_of"
            and r.get("method") == "demo_rule"
            and r.get("evidence", {}).get("basis") == "docvortex_public_postprocess"
            and not r.get("evidence", {}).get("manual")
        ]
        prior_ids = {r["id"] for r in prior_links}
        candidate["relations"] = [r for r in candidate["relations"] if r["id"] not in prior_ids]
        continuations: list[tuple[str, str]] = []
        lookup = {(e["page_index"], e["raw_index"]): e for e in value.ledger["entries"]}
        mapped: dict[str, Json] = {}
        losses: list[Json] = []
        proposals: list[Json] = []
        caption_groups: list[tuple[str, Json, Json | None, int]] = []
        for page in middle["pages"]:
            for parent in page["blocks"]:
                for leaf in leaves(parent):
                    entry = lookup.get((page["page_idx"], leaf.get("index")))
                    if entry is None:
                        losses.append(
                            {"code": "UNMAPPED_SHARED_BLOCK", "page_index": page["page_idx"]}
                        )
                        continue
                    bid = entry["source_id"]
                    if bid in mapped:
                        mapped[bid]["preserved"] = False
                        losses.append({"code": "DUPLICATE_SHARED_SOURCE", "source_id": bid})
                        continue
                    raw = entry["raw"]
                    preserved = (
                        leaf.get("bbox") == raw["bbox"]
                        and inline_text(leaf.get("content")) == inline_text(raw["content"])
                        and leaf.get("image_path") == raw.get("image_path")
                    )
                    mapped[bid] = {"preserved": preserved, "leaf": leaf, "entry": entry}
                    removed = [
                        k
                        for k in ("lines", "angle", "score", "label")
                        if k in raw and k not in leaf
                    ]
                    if removed:
                        losses.append(
                            {
                                "code": "TEMP_FIELDS_REMOVED_RETAINED_IN_LEDGER",
                                "source_id": bid,
                                "fields": removed,
                            }
                        )
                    if not preserved:
                        losses.append(
                            {"code": "SHARED_CONTENT_OR_GEOMETRY_CHANGED", "source_id": bid}
                        )
                    if parent["type"] in {"image", "table"} and leaf["type"].endswith("caption"):
                        owner = lookup.get((page["page_idx"], parent["index"]))
                        caption_groups.append((bid, entry, owner, parent["index"]))
        # Group adoption needs the final fidelity state of both members, including duplicates.
        for bid, entry, owner, parent_index in caption_groups:
            confirmed = bool(
                mapped.get(bid, {}).get("preserved")
                and owner
                and mapped.get(owner["source_id"], {}).get("preserved")
                and not locked(entry["block"])
                and not locked(owner["block"])
                and any(
                    r["type"] == "caption_of" and r["from"] == bid and r["to"] == owner["source_id"]
                    for r in selected["relations"]
                )
            )
            proposals.append(
                {
                    "source_id": bid,
                    "kind": "caption_group",
                    "parent_index": parent_index,
                    "adopted": confirmed,
                    "reason": "existing_explicit_ownership"
                    if confirmed
                    else "ownership_requires_review",
                }
            )
            if not confirmed:
                losses.append({"code": "SHARED_CAPTION_OWNERSHIP_UNCONFIRMED", "source_id": bid})
        for entry in value.ledger["entries"]:
            bid = entry["source_id"]
            if bid not in mapped:
                losses.append({"code": "SHARED_SOURCE_MISSING", "source_id": bid})
        previous: Any = None
        for entry in value.ledger["entries"]:
            bid, b = entry["source_id"], entry["block"]
            match = mapped.get(bid, {})
            leaf = match.get("leaf", {})
            safe = bool(match.get("preserved")) and not locked(b)
            if leaf.get("level") is not None:
                proposals.append(
                    {
                        "source_id": bid,
                        "kind": "heading_level",
                        "value": leaf["level"],
                        "adopted": safe,
                        "basis": "upstream_default_not_model_detection",
                    }
                )
            if leaf.get("continues_prev"):
                can_continue = bool(
                    safe
                    and previous
                    and previous["block"]["type"] == "paragraph"
                    and b["type"] == "paragraph"
                    and not locked(previous["block"])
                    and entry["page_index"] - previous["page_index"] in {0, 1}
                    and entry["raw"].get("lines")
                    and previous["raw"].get("lines")
                    and mapped.get(previous["source_id"], {}).get("preserved")
                )
                rejection = (
                    continuation_rejection(selected, bid, previous["source_id"])
                    if previous
                    else "RELATION_SOURCE_UNKNOWN"
                )
                can_continue = can_continue and rejection is None
                proposals.append(
                    {
                        "source_id": bid,
                        "kind": "continues_prev",
                        "adopted": can_continue,
                        "reason": rejection
                        if rejection
                        else "source_bound_continuation"
                        if can_continue
                        else "shared_fidelity_unproven",
                    }
                )
                if rejection:
                    losses.append({"code": rejection, "source_id": bid})
                if can_continue:
                    continuations.append((bid, previous["source_id"]))
            previous = entry

        def exists(origin: str, target: str) -> bool:
            return any(
                r["type"] == "continuation_of" and r["from"] == origin and r["to"] == target
                for r in candidate["relations"]
            )

        # Reuse stable IDs before allocating new ones, so new edges cannot steal an old ID.
        for origin, target in continuations:
            old = next((r for r in prior_links if r["from"] == origin and r["to"] == target), None)
            if old is not None and not exists(origin, target):
                restored = copy.deepcopy(old)
                restored["evidence"]["ledger_sha256"] = json_hash(value.ledger)
                candidate["relations"].append(restored)
        for origin, target in continuations:
            if not exists(origin, target):
                relation(
                    candidate,
                    "continuation_of",
                    origin,
                    target,
                    {
                        "basis": "docvortex_public_postprocess",
                        "ledger_sha256": json_hash(value.ledger),
                    },
                )
                added = candidate["relations"][-1]
                if added["id"] in prior_ids:
                    reserved = prior_ids | {r["id"] for r in candidate["relations"]}
                    index = len(reserved)
                    while f"rel-{index}" in reserved:
                        index += 1
                    added["id"] = f"rel-{index}"
        retired_ids = prior_ids - {r["id"] for r in candidate["relations"]}
        for page in candidate["pages"]:
            for block in page["blocks"]:
                block["relations"] = [rid for rid in block["relations"] if rid not in retired_ids]
        prior_issue_records = (
            selected.get("metadata", {})
            .get("docvortex_structure", {})
            .get("emitted_issue_records", [])
        )
        owned_issues = {item["id"]: item for item in prior_issue_records}
        # Only untouched stage records may be replaced. Human edits and unrelated issues survive.
        retained_issues = [
            item for item in candidate["issues"] if item != owned_issues.get(item["id"])
        ]
        candidate["issues"] = []
        emitted_issue_records: list[Json] = []
        reserved_issue_ids = {item["id"] for item in selected["issues"]}

        def issue_key(item: Json) -> tuple[str, int, tuple[str, ...]]:
            return item["type"], item["page_index"], tuple(item["block_ids"])

        page_by_source = {e["source_id"]: e["page_index"] for e in value.ledger["entries"]}
        for loss in losses:
            if loss["code"] != "TEMP_FIELDS_REMOVED_RETAINED_IN_LEDGER":
                bid = loss.get("source_id")
                issue(
                    candidate,
                    loss["code"],
                    "共享候选未满足保真约束；保留原内容与来源待复核。",
                    [bid] if bid else [],
                    page_by_source.get(
                        bid, loss.get("page_index", selected["pages"][0]["page_index"])
                    ),
                )
        fresh_issues = candidate["issues"]
        candidate["issues"] = retained_issues
        # Allocate after matching old IDs, reserving all historical IDs for this pass.
        for fresh in fresh_issues:
            if any(issue_key(item) == issue_key(fresh) for item in candidate["issues"]):
                continue
            old = next(
                (item for item in prior_issue_records if issue_key(item) == issue_key(fresh)), None
            )
            if old is not None and all(item["id"] != old["id"] for item in candidate["issues"]):
                fresh["id"] = old["id"]
            else:
                index = len(reserved_issue_ids)
                while f"issue-{index}" in reserved_issue_ids:
                    index += 1
                fresh["id"] = f"issue-{index}"
            reserved_issue_ids.add(fresh["id"])
            candidate["issues"].append(fresh)
            emitted_issue_records.append(copy.deepcopy(fresh))
        conservation = verify_shared(selected, candidate)
        report = {
            "status": "GUARDED",
            "conservation": conservation,
            "losses": losses,
            "proposals": proposals,
            "input_ir_sha256": json_hash(selected),
            "source_ledger_sha256": json_hash(value.ledger),
            "model_sha256": json_hash(value.model),
            "middle_sha256": json_hash(middle),
            "retired_stage_relation_ids": sorted(retired_ids),
            "emitted_issue_records": emitted_issue_records,
            "source_count": len(lookup),
            "mapped_count": len(mapped),
            "model_call_count": 0,
        }
        candidate["metadata"]["docvortex_structure"] = {
            "stage": "finalized",
            **report,
            "finalized_ir_sha256": finalized_hash(candidate),
        }
        self.last_execution = {
            "model": value.model,
            "middle": middle,
            "source_ledger": value.ledger,
            "loss_report": report,
            "worker": {k: v for k, v in result.items() if k not in {"middle", "model_roundtrip"}},
        }
        validate(candidate)
        return StructureCandidate(candidate, report)
