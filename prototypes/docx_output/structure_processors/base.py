"""Structure candidates are separate from selected evidence and output plans."""
from dataclasses import dataclass
from typing import Protocol

from ..common import Json


@dataclass
class StructureCandidate:
    """A proposed Layout IR and explicit mapping loss report."""

    document: Json
    loss_report: Json


class StructureProcessor(Protocol):
    """Process already selected evidence, independently of the renderer."""

    name: str
    version: str

    def process(self, selected: Json) -> StructureCandidate:
        """Return an owned candidate without mutating evidence or requesting models."""
        ...
