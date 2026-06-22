from dataclasses import dataclass
from typing import Any

import httpx

from companion_bot.config import LLMSettings
from companion_bot.http import DEFAULT_HTTP_TIMEOUT_SECONDS


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


class LLMClientError(RuntimeError):
    """Raised when the LLM provider cannot return a usable reply."""


def _build_deepseek_body(
    messages: list[ChatMessage], settings: LLMSettings
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": settings.model,
        "messages": [
            {"role": message.role, "content": message.content} for message in messages
        ],
        "reasoning_effort": settings.reasoning_effort,
        "stream": False,
    }
    if settings.thinking_enabled:
        body["thinking"] = {"type": "enabled"}
    return body


def _parse_deepseek_reply(payload: dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMClientError("Invalid DeepSeek response") from exc

    if not isinstance(content, str) or not content.strip():
        raise LLMClientError("Invalid DeepSeek response")

    return content


async def generate_chat_reply(
    messages: list[ChatMessage], settings: LLMSettings
) -> str:
    if settings.provider != "deepseek":
        raise LLMClientError(f"Unsupported LLM provider: {settings.provider}")

    try:
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{settings.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.api_key}"},
                json=_build_deepseek_body(messages, settings),
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise LLMClientError("DeepSeek request failed") from exc
    except ValueError as exc:
        raise LLMClientError("Invalid DeepSeek response") from exc

    return _parse_deepseek_reply(payload)
