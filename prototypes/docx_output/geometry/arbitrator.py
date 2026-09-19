"""Conservative macro selection from independently bound content support."""

from __future__ import annotations

import copy
from itertools import pairwise

from ..common import DemoError, Json, area, intersection, union
from ..structure_processors.bridge import json_hash
from ..structure_processors.docvortex import locked
from .binding import identity_bindings, validate_transition
from .candidate import rectangle
from .order import column_order

POLICY: Json = {
    "version": "geometry-arbitration/1",
    "minimum_support_coverage": 0.98,
    "maximum_text_expansion": 2.5,
    "minimum_figure_iou": 0.85,
    "unknown_support": "abstain",
    "multiple_valid_providers": "abstain",
}


def supported_kind(candidate: Json, block: Json) -> bool:
    """Do not turn a caption into body text or an image into recognized text."""
    label = candidate["label"].lower()
    if block["content"]["kind"] == "image":
        return label in {"picture", "image", "figure", "chart"}
    if block["type"] == "caption":
        return label in {"caption", "figure_title", "image_caption"}
    if block["type"] in {"footer", "page_number"}:
        return label in {"footer", "page-footer", "number", "page_number"}
    return block["content"]["kind"] == "text" and label in {
        "text",
        "paragraph",
        "section-header",
        "paragraph_title",
        "doc_title",
        "list-item",
        "heading",
        "number",
        "page-footer",
        "footer",
    }


class GeometryArbitrator:
    """Choose a coherent provider only when every source block has independent support."""

    def propose(self, page: Json, supports: Json) -> tuple[Json, Json]:
        """Return owned page and audit; no provider/body/network access or probability fiction."""
        report: Json = {
            "policy": POLICY,
            "policy_sha256": json_hash(POLICY),
            "selected_provider": None,
            "decisions": [],
            "status": "ABSTAIN",
        }
        valid: list[tuple[str, Json, Json]] = []
        for provider in ("monkey", "pp"):
            candidates = [
                c
                for c in page.get("geometry_candidates", [])
                if c["provider"] == provider
                and c["hierarchy_level"] == "region"
                and c["granularity"] == "semantic_region"
            ]
            if not candidates:
                report["decisions"].append({"provider": provider, "reason": "NO_MACRO_CANDIDATES"})
                continue
            try:
                projected, bindings = self._project(page, candidates, supports)
                order = column_order(page, supports)
                if order["status"] == "PROVEN":
                    projected["reading_order"] = order["order"]
                proof = validate_transition(
                    page, projected, identity_bindings(page), order["edges"]
                )
                proof["column_order"] = order
                valid.append((provider, projected, {"bindings": bindings, "content_proof": proof}))
                report["decisions"].append({"provider": provider, "reason": "ELIGIBLE"})
            except (DemoError, ValueError) as exc:
                report["decisions"].append({"provider": provider, "reason": str(exc)})
        if len(valid) != 1:
            report["reason"] = "MULTIPLE_VALID_PROVIDERS" if valid else "NO_PROVEN_PROVIDER"
            return copy.deepcopy(page), report
        provider, projected, proof = valid[0]
        report.update(status="SELECTED", selected_provider=provider, **proof)
        return projected, report

    def _project(self, page: Json, candidates: list[Json], supports: Json) -> tuple[Json, Json]:
        """Apply a page-wide macro choice; never compare glyph/line boxes as macro rivals."""
        boxes: list[list[float]] = []
        ids = set()
        for candidate in candidates:
            box = rectangle(candidate["bbox_pt"])
            if (
                candidate["page_index"] != page["page_index"]
                or candidate["transform_chain"]["target"] != "visible_rotated_top_left_pt"
                or not (
                    0 <= box[0] < box[2] <= page["width_pt"]
                    and 0 <= box[1] < box[3] <= page["height_pt"]
                )
                or candidate["id"] in ids
            ):
                raise DemoError("INVALID_MACRO_FRAME_OR_ID")
            if any(intersection(box, old) / min(area(box), area(old)) > 0.1 for old in boxes):
                raise DemoError("OVERLAPPING_MACRO_REGIONS")
            boxes.append(box)
            ids.add(candidate["id"])
        projected = copy.deepcopy(page)
        bindings = {}
        claimed: dict[str, list[str]] = {}
        for block in projected["blocks"]:
            bid = block["id"]
            if locked(block):
                bindings[bid] = {"status": "MANUAL_LOCK_PRESERVED"}
                continue
            if bid not in supports:
                raise DemoError("CONTENT_SUPPORT_MISSING")
            support = supports[bid]
            if support.get("basis") not in {
                "native_verified_run",
                "exact_pp_text",
                "exact_pp_line_spans",
                "source_figure",
            }:
                raise DemoError("CONTENT_SUPPORT_UNPROVEN")
            if support.get("source_content_sha256") != json_hash(block["content"]):
                raise DemoError("CONTENT_SUPPORT_STALE")
            box = rectangle(support["bbox_pt"])
            matches = []
            for candidate in candidates:
                if not supported_kind(candidate, block):
                    continue
                proposed = candidate["bbox_pt"]
                overlap = intersection(box, proposed)
                if block["content"]["kind"] == "image":
                    if (
                        overlap / (area(box) + area(proposed) - overlap)
                        < POLICY["minimum_figure_iou"]
                    ):
                        continue
                elif (
                    overlap / area(box) < POLICY["minimum_support_coverage"]
                    or area(proposed) / area(box) > POLICY["maximum_text_expansion"]
                ):
                    continue
                matches.append(candidate)
            if len(matches) != 1:
                raise DemoError("AMBIGUOUS_OR_MISSING_BINDING")
            selected = matches[0]
            claimed.setdefault(selected["id"], []).append(bid)
            # A native measured run stays where it was; model geometry is its semantic parent.
            if block["geometry_source"] != "native_pdf":
                block["bbox"] = union([box, selected["bbox_pt"]])
                block["geometry_source"] = "fused"
                block["selected_geometry_id"] = selected["id"]
            bindings[bid] = {
                "status": "BOUND",
                "geometry_id": selected["id"],
                "support": copy.deepcopy(support),
                "native_measurement_preserved": block["geometry_source"] == "native_pdf",
                "bbox_pt": block["bbox"],
            }
        if any(len(owners) > 1 for owners in claimed.values()):
            raise DemoError("MACRO_MERGE_REQUIRES_SPAN_BINDING")
        return projected, bindings


def project_explicit_order(
    page: Json, order: list[str], edges: list[list[str]]
) -> tuple[Json, Json]:
    """Validate a separately evidenced order proposal; never invent model order keys."""
    projected = copy.deepcopy(page)
    projected["reading_order"] = list(order)
    proof = validate_transition(page, projected, identity_bindings(page), edges)
    # The caller must retain the actual edge evidence alongside this content proof.
    proof["order_coverage"] = [list(pair) for pair in pairwise(order)]
    return projected, proof
