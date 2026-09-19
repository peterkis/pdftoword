"""Flow renderer reusing the existing editable content and source-map writer."""

from pathlib import Path

from ..common import DemoError, Json
from ..planning.render_plan import RenderPlan
from ..writer import build


class FlowRenderer:
    """Apply explicit output nodes while retaining source geometry and content."""

    name = "flow"
    version = "1"

    def render(self, job: Path, plan: RenderPlan, revision: str) -> Json:
        """No layout inference or model calls occur in the renderer."""
        if plan.output_layout.get("mode") != "flow_v1":
            raise DemoError("FLOW_PLAN_REQUIRED")
        plan.as_dict()
        return build(job, plan.document, revision, output_plan=plan.output_layout)
