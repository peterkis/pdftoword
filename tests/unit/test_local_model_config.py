"""Local FRP configuration and compatibility with existing Gate variables."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from model_contract_discovery import load_config, openai_endpoint_url


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate tests from developer credentials and endpoint overrides."""
    monkeypatch.chdir(tmp_path)
    for prefix in ("MONKEY", "OVIS", "PP", "PADDLE"):
        for suffix in ("BASE_URL", "OPENAI_BASE_URL", "STRUCTURE_BASE_URL", "CHAT_URL",
                       "STRUCTURE_URL", "API_KEY"):
            monkeypatch.delenv(f"{prefix}_{suffix}", raising=False)
    return tmp_path


def test_frp_root_urls(isolated_env: Path) -> None:
    """Quoted service roots produce valid OpenAI paths without duplicate v1."""
    (isolated_env / ".env.local").write_text(
        'MONKEY_BASE_URL="http://127.0.0.1:9000"\n'
        "OVIS_BASE_URL='http://127.0.0.1:8000'\n"
        "PP_BASE_URL=http://127.0.0.1:8080\n", encoding="utf-8",
    )
    config = load_config()
    assert openai_endpoint_url(config.monkey.base_url, "models") == (
        "http://127.0.0.1:9000/v1/models"
    )
    assert openai_endpoint_url(config.ovis.base_url, "chat/completions") == (
        "http://127.0.0.1:8000/v1/chat/completions"
    )
    assert config.pp.base_url == "http://127.0.0.1:8080"


def test_environment_beats_file_alias(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A legacy environment override takes priority over the local file."""
    (isolated_env / ".env.local").write_text(
        "MONKEY_BASE_URL=http://file.example:9000\n", encoding="utf-8",
    )
    monkeypatch.setenv("MONKEY_OPENAI_BASE_URL", "http://override.example:9000/v1")
    assert load_config().monkey.base_url == "http://override.example:9000/v1"


def test_new_alias_beats_legacy_in_same_source(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit short names win when both names exist in the environment."""
    monkeypatch.setenv("OVIS_BASE_URL", "http://new.example:8000")
    monkeypatch.setenv("OVIS_OPENAI_BASE_URL", "http://old.example:8000/v1")
    assert load_config().ovis.base_url == "http://new.example:8000"


def test_legacy_file_still_supported(isolated_env: Path) -> None:
    """Existing Gate configurations remain usable."""
    (isolated_env / ".env.local").write_text(
        "PP_STRUCTURE_BASE_URL=http://legacy.example:8080\n", encoding="utf-8",
    )
    assert load_config().pp.base_url == "http://legacy.example:8080"
