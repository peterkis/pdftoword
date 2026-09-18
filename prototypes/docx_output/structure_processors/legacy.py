"""Executable pass-through for structure already recovered by the S2 pipeline."""
import copy

from ..common import Json, validate
from .base import StructureCandidate


class LegacyStructureProcessor:
    """Retain current blocks, order, relationships and human locks verbatim."""

    name = "legacy"
    version = "1"

    def process(self, selected: Json) -> StructureCandidate:
        """Forward validated selected evidence with no structural transformation."""
        validate(selected)
        return StructureCandidate(copy.deepcopy(selected), {"status": "IDENTITY", "losses": []})
