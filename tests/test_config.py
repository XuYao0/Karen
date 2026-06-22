from importlib import import_module
from pathlib import Path
import tomllib

import pytest

from companion_bot.config import (
    ChatSettings,
    GatewaySettings,
    LLMSettings,
    load_chat_settings,
    load_gateway_settings,
    load_llm_settings,
)
from companion_bot.http import normalize_base_url


@pytest.fixture(autouse=True)
def clear_llm_env(monkeypatch):
    for key in (
        "DEEPSEEK_API_KEY",
        "LLM_PROVIDER",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "LLM_REASONING_EFFORT",
        "LLM_THINKING_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)


def test_load_gateway_settings_requires_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("CHAT_SERVICE_URL", raising=False)

    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        load_gateway_settings()


def test_load_gateway_settings_uses_default_chat_url(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-123")
    monkeypatch.delenv("CHAT_SERVICE_URL", raising=False)

    settings = load_gateway_settings()

    assert settings == GatewaySettings(
        telegram_bot_token="token-123",
        chat_service_url="http://127.0.0.1:8002",
    )


def test_load_chat_settings_uses_default_memory_url(monkeypatch):
    monkeypatch.delenv("MEMORY_SERVICE_URL", raising=False)

    settings = load_chat_settings()

    assert settings == ChatSettings(memory_service_url="http://127.0.0.1:8001")


def test_normalize_base_url_strips_trailing_slash():
    assert normalize_base_url("http://localhost:8000/") == "http://localhost:8000"


def test_setuptools_packages_include_service_subpackage():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())

    assert data["tool"]["setuptools"]["packages"] == [
        "companion_bot",
        "companion_bot.services",
    ]


def test_service_module_is_importable():
    module = import_module("companion_bot.services.memory")

    assert module is not None


def test_load_llm_settings_requires_deepseek_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        load_llm_settings()


def test_load_llm_settings_uses_deepseek_defaults(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("LLM_THINKING_ENABLED", raising=False)

    settings = load_llm_settings()

    assert settings == LLMSettings(
        provider="deepseek",
        api_key="deepseek-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-pro",
        reasoning_effort="high",
        thinking_enabled=True,
    )


def test_load_llm_settings_normalizes_base_url(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com/")

    settings = load_llm_settings()

    assert settings.base_url == "https://api.deepseek.com"


def test_load_llm_settings_rejects_unsupported_provider(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    with pytest.raises(RuntimeError, match="Unsupported LLM_PROVIDER"):
        load_llm_settings()


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("0", False),
        ("no", False),
    ],
)
def test_load_llm_settings_parses_thinking_enabled(
    monkeypatch, raw_value, expected
):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("LLM_THINKING_ENABLED", raw_value)

    settings = load_llm_settings()

    assert settings.thinking_enabled is expected
