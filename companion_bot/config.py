from dataclasses import dataclass
import os

from companion_bot.http import normalize_base_url

DEFAULT_CHAT_SERVICE_URL = "http://127.0.0.1:8002"
DEFAULT_MEMORY_SERVICE_URL = "http://127.0.0.1:8001"
DEFAULT_LLM_PROVIDER = "deepseek"
DEFAULT_LLM_BASE_URL = "https://api.deepseek.com"
DEFAULT_LLM_MODEL = "deepseek-v4-pro"
DEFAULT_LLM_REASONING_EFFORT = "high"


@dataclass(frozen=True)
class GatewaySettings:
    telegram_bot_token: str
    chat_service_url: str


@dataclass(frozen=True)
class ChatSettings:
    memory_service_url: str


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    api_key: str
    base_url: str
    model: str
    reasoning_effort: str
    thinking_enabled: bool


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"Invalid boolean value: {value}")


def load_gateway_settings() -> GatewaySettings:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start telegram-gateway")

    return GatewaySettings(
        telegram_bot_token=token,
        chat_service_url=normalize_base_url(
            os.getenv("CHAT_SERVICE_URL", DEFAULT_CHAT_SERVICE_URL)
        ),
    )


def load_chat_settings() -> ChatSettings:
    return ChatSettings(
        memory_service_url=normalize_base_url(
            os.getenv("MEMORY_SERVICE_URL", DEFAULT_MEMORY_SERVICE_URL)
        )
    )


def load_llm_settings() -> LLMSettings:
    provider = os.getenv("LLM_PROVIDER", DEFAULT_LLM_PROVIDER).strip().lower()
    if provider != "deepseek":
        raise RuntimeError(f"Unsupported LLM_PROVIDER: {provider}")

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required for DeepSeek LLM calls")

    return LLMSettings(
        provider=provider,
        api_key=api_key,
        base_url=normalize_base_url(os.getenv("LLM_BASE_URL", DEFAULT_LLM_BASE_URL)),
        model=os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL),
        reasoning_effort=os.getenv("LLM_REASONING_EFFORT", DEFAULT_LLM_REASONING_EFFORT),
        thinking_enabled=_parse_bool(os.getenv("LLM_THINKING_ENABLED", "true")),
    )
