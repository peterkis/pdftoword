"""Output-only renderer boundary; no provider or structure processing dependency."""
from pathlib import Path
from typing import Protocol

from ..common import Json
from ..planning.render_plan import RenderPlan


class DocxRenderer(Protocol):
    """Consume a plan and local assets, returning the existing package audit statistics."""

    name: str
    version: str

    def render(self, job: Path, plan: RenderPlan, revision: str) -> Json:
        """Write one DOCX and source map without inference."""
        ...
