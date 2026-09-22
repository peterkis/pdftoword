"""Explicit output-only candidates, independent of recognition routing and authorization."""

from __future__ import annotations

import copy

from .common import ROOT, DemoError, Json, read

OUTPUT_PROFILES = ("legacy", "fidelity-v3.1")


def select_output_profile(ir: Json, name: str) -> None:
    """Freeze the named candidate settings in IR without changing any source block."""
    if name not in OUTPUT_PROFILES:
        raise DemoError("UNKNOWN_OUTPUT_PROFILE")
    if name != "legacy":
        ir["metadata"]["output_profile"] = read(ROOT / f"config/profiles/{name}.json")


def output_settings(ir: Json) -> Json | None:
    """Reuse persisted settings on review; existing per-job style edits take precedence."""
    profile = ir["metadata"].get("output_profile")
    if profile is None:
        return None
    if not isinstance(profile, dict) or profile.get("id") != "fidelity-v3.1":
        raise DemoError("UNKNOWN_OUTPUT_PROFILE")
    settings = profile.get("settings")
    if not isinstance(settings, dict):
        raise DemoError("INVALID_OUTPUT_PROFILE_SETTINGS")
    return {**copy.deepcopy(settings), **ir.get("planning", {}).get("profile_settings", {})}
