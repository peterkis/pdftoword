"""Lossless minimal output plan; content stays in validated Layout IR."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from ..common import DemoError, Json, validate

PLAN_VERSION = "render-plan/1"
LEGACY_LAYOUT = {"mode": "legacy_flow", "paper_pt": [595.28, 841.89],
                 "margins_pt": [40, 45, 40, 45], "pagination": "natural"}


@dataclass
class RenderPlan:
    """Owned IR snapshot plus explicit supported output layout and style references."""

    document: Json
    output_layout: Json

    @classmethod
    def from_ir(cls, ir: Json) -> RenderPlan:
        """Keep every candidate, lock, relation and inline part without a lossy projection."""
        validate(ir)
        return cls(copy.deepcopy(ir), copy.deepcopy(LEGACY_LAYOUT))

    def as_dict(self) -> Json:
        """Serialize content, source IDs, source styles and legacy output style bindings."""
        return {"schema_version": PLAN_VERSION, "document": copy.deepcopy(self.document),
                "output_layout": copy.deepcopy(self.output_layout),
                "elements": [
                    {"source_ids": [b["id"]], "content": copy.deepcopy(b["content"]),
                     "style_ref": "Heading 1" if b["type"] == "heading" else
                     "Caption" if b["type"] in {"caption", "footer"} else "Normal",
                     "source_style_ref": b.get("style_ref")}
                    for p in self.document["pages"]
                    for by_id in [{b["id"]: b for b in p["blocks"]}]
                    for bid in p["reading_order"] for b in [by_id[bid]]]}

    def legacy_ir(self) -> Json:
        """Reject unsupported layout instead of silently dropping plan directives."""
        if self.output_layout != LEGACY_LAYOUT:
            raise DemoError("LEGACY_LAYOUT_UNSUPPORTED")
        validate(self.document)
        return copy.deepcopy(self.document)
