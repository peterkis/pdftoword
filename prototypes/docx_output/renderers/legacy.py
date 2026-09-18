"""Compatibility adapter around the existing flowing writer."""
from pathlib import Path

from ..common import Json
from ..planning.render_plan import RenderPlan
from ..writer import build


class LegacyRenderer:
    """Preserve the current writer's semantics and illustration safeguards."""

    name = "legacy"
    version = "1"

    def render(self, job: Path, plan: RenderPlan, revision: str) -> Json:
        """Forward a supported plan to the original writer."""
        return build(job, plan.legacy_ir(), revision)
