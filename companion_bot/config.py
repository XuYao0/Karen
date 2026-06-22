from dataclasses import dataclass
import os

from companion_bot.http import normalize_base_url

DEFAULT_CHAT_SERVICE_URL = "http://127.0.0.1:8002"
DEFAULT_MEMORY_SERVICE_URL = "http://127.0.0.1:8001"


@dataclass(frozen=True)
class GatewaySettings:
    telegram_bot_token: str
    chat_service_url: str


@dataclass(frozen=True)
class ChatSettings:
    memory_service_url: str


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
