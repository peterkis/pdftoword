"""Provider configuration schema for PDF2Word Local V1.1.

Re-exports the declarative structures defined in ``providers`` so that
callers can import everything from ``pdf2word_core_domain.config``.
"""

from __future__ import annotations

from .providers import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    EndpointProfile,
    ModelProviderConfig,
    ProviderCapability,
    ProviderStatus,
    ProviderType,
    TransportProfile,
    default_endpoint_profile,
)

__all__ = [
    "DEFAULT_CONNECT_TIMEOUT_SECONDS",
    "DEFAULT_REQUEST_TIMEOUT_SECONDS",
    "EndpointProfile",
    "ModelProviderConfig",
    "ProviderCapability",
    "ProviderStatus",
    "ProviderType",
    "TransportProfile",
    "default_endpoint_profile",
]
