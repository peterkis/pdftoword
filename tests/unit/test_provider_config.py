"""Schema tests for the T0001 provider configuration skeleton.

These tests verify that the declarative structures can be instantiated,
that endpoint paths may stay empty and transport profiles may stay
``auto`` (PP-StructureV3 contract is intentionally not frozen yet), and
that invalid values are rejected instead of silently accepted.
"""

from __future__ import annotations

import dataclasses

import pytest

from pdf2word_core_domain.config import (
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


def test_endpoint_profile_defaults() -> None:
    profile = EndpointProfile(base_url="http://model-server.example:8100")
    assert profile.endpoint_path == ""
    assert profile.transport is TransportProfile.AUTO
    assert profile.connect_timeout_seconds == DEFAULT_CONNECT_TIMEOUT_SECONDS
    assert profile.request_timeout_seconds == DEFAULT_REQUEST_TIMEOUT_SECONDS


def test_endpoint_path_may_stay_empty() -> None:
    profile = EndpointProfile(
        base_url="http://model-server.example:8080",
        endpoint_path="",
    )
    assert profile.endpoint_path == ""


def test_transport_profile_can_be_auto() -> None:
    assert TransportProfile("auto") is TransportProfile.AUTO
    profile = EndpointProfile(
        base_url="http://model-server.example:8080",
        transport=TransportProfile.AUTO,
    )
    assert profile.transport is TransportProfile.AUTO


def test_endpoint_path_must_start_with_slash_when_set() -> None:
    with pytest.raises(ValueError, match="endpoint_path"):
        EndpointProfile(
            base_url="http://model-server.example:8080",
            endpoint_path="layout-parsing",
        )


def test_base_url_requires_http_scheme() -> None:
    with pytest.raises(ValueError, match="base_url"):
        EndpointProfile(base_url="model-server.example:8080")


def test_base_url_may_contain_stable_api_prefix() -> None:
    profile = EndpointProfile(
        base_url="http://model-server.example:9000/v1",
        endpoint_path="/chat/completions",
    )
    assert profile.base_url == "http://model-server.example:9000/v1"
    assert profile.endpoint_path == "/chat/completions"


def test_base_url_rejects_query_string() -> None:
    with pytest.raises(ValueError, match="query"):
        EndpointProfile(base_url="http://model-server.example:9000/v1?token=x")


def test_base_url_rejects_fragment() -> None:
    with pytest.raises(ValueError, match="fragment"):
        EndpointProfile(base_url="http://model-server.example:9000/v1#section")


def test_base_url_requires_host() -> None:
    with pytest.raises(ValueError, match="host"):
        EndpointProfile(base_url="http://")


def test_timeouts_must_be_positive() -> None:
    with pytest.raises(ValueError, match="connect_timeout_seconds"):
        EndpointProfile(
            base_url="http://model-server.example:8080",
            connect_timeout_seconds=0,
        )
    with pytest.raises(ValueError, match="request_timeout_seconds"):
        EndpointProfile(
            base_url="http://model-server.example:8080",
            request_timeout_seconds=-1,
        )


def test_provider_config_can_be_instantiated() -> None:
    config = ModelProviderConfig(
        provider_id="probe-provider",
        provider_type=ProviderType.OPENAI_COMPATIBLE,
        model_name="probe-model",
        endpoint=EndpointProfile(base_url="http://model-server.example:9000/v1"),
        capabilities=frozenset({ProviderCapability.LAYOUT_COMPLEX}),
        max_concurrency=1,
        status=ProviderStatus.DISABLED,
    )
    assert config.provider_id == "probe-provider"
    assert config.provider_type is ProviderType.OPENAI_COMPATIBLE
    assert config.model_name == "probe-model"
    assert config.status is ProviderStatus.DISABLED
    assert ProviderCapability.LAYOUT_COMPLEX in config.capabilities


def test_openai_compatible_provider_requires_model_name() -> None:
    with pytest.raises(ValueError, match="model_name"):
        ModelProviderConfig(
            provider_id="probe-provider",
            provider_type=ProviderType.OPENAI_COMPATIBLE,
            endpoint=EndpointProfile(base_url="http://model-server.example:9000/v1"),
        )


def test_provider_id_must_not_be_empty() -> None:
    with pytest.raises(ValueError, match="provider_id"):
        ModelProviderConfig(
            provider_id="   ",
            provider_type=ProviderType.PADDLE,
            endpoint=EndpointProfile(base_url="http://model-server.example:8080"),
        )


def test_max_concurrency_must_be_at_least_one() -> None:
    with pytest.raises(ValueError, match="max_concurrency"):
        ModelProviderConfig(
            provider_id="probe-provider",
            provider_type=ProviderType.PADDLE,
            endpoint=EndpointProfile(base_url="http://model-server.example:8080"),
            max_concurrency=0,
        )


def test_provider_config_is_immutable() -> None:
    config = ModelProviderConfig(
        provider_id="probe-provider",
        provider_type=ProviderType.PADDLE,
        endpoint=EndpointProfile(base_url="http://model-server.example:8080"),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.provider_id = "other"  # type: ignore[misc]


def test_default_endpoint_profile_loads() -> None:
    profile = default_endpoint_profile("http://model-server.example:8100")
    assert profile.endpoint_path == ""
    assert profile.transport is TransportProfile.AUTO
    assert profile.connect_timeout_seconds == DEFAULT_CONNECT_TIMEOUT_SECONDS
    assert profile.request_timeout_seconds == DEFAULT_REQUEST_TIMEOUT_SECONDS
