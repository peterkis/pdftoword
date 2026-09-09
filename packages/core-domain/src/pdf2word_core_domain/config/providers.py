"""Declarative provider configuration schema (T0001 skeleton).

This module defines the data structures used to *describe* model
providers: provider type, base URL, endpoint path, transport profile,
timeouts, concurrency, capabilities and enabled status. It deliberately
contains no runtime behavior:

- no HTTP calls, health checks or capability probing (T0010 / P0-GATE-001);
- no YAML or environment loading (T0003);
- no engine protocols (T0006).

Real addresses and API keys may only come from local configuration files
such as ``.env.local``; committing them to the repository is forbidden
(see AGENTS.md section 7 and docs/15_SECURITY_PRIVACY_LICENSE.md). Model
server addresses, ports and model names must not be hardcoded here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from urllib.parse import urlsplit

#: Default TCP connection timeout in seconds
#: (mirrors MODEL_CONNECT_TIMEOUT_SECONDS from .env.example).
DEFAULT_CONNECT_TIMEOUT_SECONDS: Final[float] = 10.0

#: Default whole-request timeout in seconds
#: (mirrors MODEL_REQUEST_TIMEOUT_SECONDS from .env.example).
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final[float] = 600.0


class ProviderType(StrEnum):
    """Kind of remote service that exposes model capabilities."""

    OPENAI_COMPATIBLE = "openai_compatible"
    PADDLE = "paddle"
    GATEWAY = "gateway"


class TransportProfile(StrEnum):
    """Wire format used to send requests to a provider endpoint.

    ``AUTO`` defers the decision to the adapter layer until the endpoint
    contract has been verified. The PP-StructureV3 transport (multipart
    file upload vs JSON + Base64) is intentionally not frozen before the
    P0-GATE-001 capability gate.
    """

    AUTO = "auto"
    MULTIPART = "multipart"
    JSON_BASE64 = "json_base64"


class ProviderCapability(StrEnum):
    """Capabilities a provider may expose, named after gateway task types."""

    LAYOUT_FAST = "layout.fast"
    LAYOUT_COMPLEX = "layout.complex"
    OCR_TEXT = "ocr.text"
    TABLE_PARSE = "parse.table"
    FORMULA_PARSE = "parse.formula"
    CONTENT_REVIEW = "review.content"


class ProviderStatus(StrEnum):
    """Whether a configured provider participates in processing."""

    ENABLED = "enabled"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class EndpointProfile:
    """Connection profile for one remote model endpoint.

    Attributes:
        base_url: Service base URL. It may contain a stable API prefix
            such as ``/v1``, but must not contain a query string,
            fragment, or a concrete operation path such as
            ``/chat/completions``.
        endpoint_path: Path of the concrete API operation, for example
            ``/chat/completions`` or ``/models``. May stay empty while
            the endpoint contract is not frozen (PP-StructureV3 before
            P0-GATE-01). When set, it must start with ``/``.
        transport: How request payloads are serialized on the wire.
            ``AUTO`` is the default and defers the decision.
        connect_timeout_seconds: TCP connection timeout in seconds.
        request_timeout_seconds: Whole-request timeout in seconds.
    """

    base_url: str
    endpoint_path: str = ""
    transport: TransportProfile = TransportProfile.AUTO
    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        _validate_base_url(self.base_url)
        _validate_endpoint_path(self.endpoint_path)
        _validate_positive("connect_timeout_seconds", self.connect_timeout_seconds)
        _validate_positive("request_timeout_seconds", self.request_timeout_seconds)


@dataclass(frozen=True, slots=True)
class ModelProviderConfig:
    """Declarative description of one model provider.

    A configuration instance only *describes* a provider; it performs no
    network activity. Providers default to ``DISABLED`` so that nothing
    is called unless explicitly enabled by configuration.

    Attributes:
        provider_id: Stable unique key, for example ``"monkey"``.
        provider_type: Kind of service exposing the capabilities.
        endpoint: Connection profile of the service.
        capabilities: Capabilities this provider offers.
        model_name: Model identifier as expected by the service. Required
            for OpenAI-compatible providers; may stay empty for pipeline
            services such as PP-StructureV3.
        max_concurrency: Maximum parallel in-flight requests. Heavy GPU
            models start at 1; concurrency is ultimately enforced by the
            model gateway, not by the client.
        status: Whether the provider participates in processing.
    """

    provider_id: str
    provider_type: ProviderType
    endpoint: EndpointProfile
    capabilities: frozenset[ProviderCapability] = frozenset()
    model_name: str = ""
    max_concurrency: int = 1
    status: ProviderStatus = ProviderStatus.DISABLED

    def __post_init__(self) -> None:
        _validate_non_empty("provider_id", self.provider_id)
        _validate_min_int("max_concurrency", self.max_concurrency, minimum=1)
        if self.provider_type is ProviderType.OPENAI_COMPATIBLE:
            _validate_non_empty("model_name", self.model_name)


def default_endpoint_profile(base_url: str) -> EndpointProfile:
    """Build an endpoint profile with safe transport defaults.

    The endpoint path stays empty and the transport profile stays
    ``AUTO`` until the real endpoint contract has been verified by the
    P0-GATE-001 capability gate.
    """
    return EndpointProfile(base_url=base_url)


def _validate_base_url(value: str) -> None:
    parsed = urlsplit(value.strip())

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("base_url must use http or https")

    if not parsed.netloc:
        raise ValueError("base_url must contain a host")

    if parsed.query or parsed.fragment:
        raise ValueError(
            "base_url must not contain query parameters or fragments"
        )


def _validate_endpoint_path(value: str) -> None:
    if value and not value.startswith("/"):
        raise ValueError(
            "endpoint_path must be empty or start with '/' "
            f"(got {value!r})"
        )


def _validate_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive (got {value!r})")


def _validate_non_empty(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must not be empty or whitespace-only")


def _validate_min_int(name: str, value: int, minimum: int) -> None:
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum} (got {value!r})")
