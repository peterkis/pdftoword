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
        lookup = {(e["page_index"], e["raw_index"]): e for e in value.ledger["entries"]}
        mapped: dict[str, Json] = {}
        losses: list[Json] = []
        proposals: list[Json] = []
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
                        confirmed = bool(
                            preserved
                            and owner
                            and not locked(entry["block"])
                            and any(
                                r["type"] == "caption_of"
                                and r["from"] == bid
                                and r["to"] == owner["source_id"]
                                for r in selected["relations"]
                            )
                        )
                        proposals.append(
                            {
                                "source_id": bid,
                                "kind": "caption_group",
                                "parent_index": parent["index"],
                                "adopted": confirmed,
                                "reason": "existing_explicit_ownership"
                                if confirmed
                                else "ownership_requires_review",
                            }
                        )
                        if not confirmed:
                            losses.append(
                                {"code": "SHARED_CAPTION_OWNERSHIP_UNCONFIRMED", "source_id": bid}
                            )
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
                proposals.append(
                    {"source_id": bid, "kind": "continues_prev", "adopted": can_continue}
                )
                if can_continue:
                    relation(
                        candidate,
                        "continuation_of",
                        bid,
                        previous["source_id"],
                        {
                            "basis": "docvortex_public_postprocess",
                            "ledger_sha256": json_hash(value.ledger),
                        },
                    )
            previous = entry
        for loss in losses:
            if loss["code"] != "TEMP_FIELDS_REMOVED_RETAINED_IN_LEDGER":
                bid = loss.get("source_id")
                issue(
                    candidate,
                    loss["code"],
                    "共享候选未满足保真约束；保留原内容与来源待复核。",
                    [bid] if bid else [],
                )
        report = {
            "status": "GUARDED",
            "losses": losses,
            "proposals": proposals,
            "input_ir_sha256": json_hash(selected),
            "source_ledger_sha256": json_hash(value.ledger),
            "model_sha256": json_hash(value.model),
            "middle_sha256": json_hash(middle),
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
