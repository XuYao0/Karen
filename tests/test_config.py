from importlib import import_module
from pathlib import Path
import tomllib

import pytest

from companion_bot.config import (
    ChatSettings,
    GatewaySettings,
    load_chat_settings,
    load_gateway_settings,
)
from companion_bot.http import normalize_base_url


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
