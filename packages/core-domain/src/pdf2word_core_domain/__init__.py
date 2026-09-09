"""PDF2Word Local V1.1 core domain package.

T0001 skeleton: provider configuration schema and reserved module
boundaries only. Layout IR, job state machine, fusion and all business
logic arrive with later P0 tickets.

This package must never depend on model SDKs, HTTP client libraries or
UI frameworks; external capabilities are reached through adapter
protocols defined in later tickets (see AGENTS.md sections 3 and 5).
"""

from __future__ import annotations

__version__ = "0.1.0"
