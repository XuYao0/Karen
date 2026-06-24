import logging
import json
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

from companion_bot.config import load_chat_settings, load_llm_settings
from companion_bot.http import DEFAULT_HTTP_TIMEOUT_SECONDS
from companion_bot.llm import ChatMessage, LLMClientError, generate_chat_reply

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Karen, a warm and emotionally present AI friend. "
    "Reply naturally and briefly."
)
LLM_FALLBACK_REPLY = (
    "我在认真想怎么回应你，但刚刚有点卡住了。你可以再发我一次，我会继续陪你。"
)


class ChatReplyRequest(BaseModel):
    user_id: str
    channel: str
    message_text: str
    message_timestamp: str | None = None


class ChatReplyResponse(BaseModel):
    reply_text: str


class MemoryContextResponse(BaseModel):
    user_id: str
    context: dict[str, Any]


class ConversationTurnResponse(BaseModel):
    updated: bool
    memory_update: dict[str, Any]


app = FastAPI(title="companion-chat-service")


async def fetch_memory_context(
    request: ChatReplyRequest, memory_service_url: str
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{memory_service_url}/v1/users/{request.user_id}/memory/context",
                json={
                    "channel": request.channel,
                    "message_text": request.message_text,
                    "message_timestamp": request.message_timestamp,
                },
            )
            response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Failed to fetch memory context for user_id=%s", request.user_id)
        return {}

    try:
        return MemoryContextResponse.model_validate(response.json()).context
    except (ValueError, TypeError):
        logger.exception("Invalid memory context payload for user_id=%s", request.user_id)
        return {}


def format_memory_context_message(context: dict[str, Any]) -> ChatMessage | None:
    if not _has_memory_context(context):
        return None
    content = (
        "Known memory context before the latest user message:\n"
        f"{json.dumps(context, ensure_ascii=False, separators=(',', ':'))}\n"
        "Use it only as background. Do not claim certainty beyond it."
    )
    return ChatMessage(role="system", content=content)


def _has_memory_context(context: dict[str, Any]) -> bool:
    return bool(
        context.get("speaker_state")
        or context.get("recent_current_events")
        or context.get("compressed_events")
        or context.get("known_characters")
    )


async def store_conversation_turn(
    request: ChatReplyRequest, reply_text: str, memory_service_url: str
) -> None:
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{memory_service_url}/v1/users/{request.user_id}/memory/turns",
                json={
                    "channel": request.channel,
                    "message_text": request.message_text,
                    "message_timestamp": request.message_timestamp,
                    "assistant_reply": reply_text,
                },
            )
            response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Failed to store conversation turn for user_id=%s", request.user_id)


async def build_reply(request: ChatReplyRequest, memory_context: dict[str, Any]) -> str:
    provider = "unknown"
    model = "unknown"
    try:
        settings = load_llm_settings()
        provider = settings.provider
        model = settings.model
        messages = [ChatMessage(role="system", content=SYSTEM_PROMPT)]
        memory_message = format_memory_context_message(memory_context)
        if memory_message is not None:
            messages.append(memory_message)
        messages.append(ChatMessage(role="user", content=request.message_text))
        return await generate_chat_reply(
            messages=messages,
            settings=settings,
        )
    except (RuntimeError, LLMClientError) as exc:
        logger.exception(
            "Failed to generate LLM reply for provider=%s model=%s user_id=%s "
            "channel=%s error_type=%s",
            provider,
            model,
            request.user_id,
            request.channel,
            type(exc).__name__,
        )
        return LLM_FALLBACK_REPLY


@app.post("/v1/chat/reply", response_model=ChatReplyResponse)
async def reply(request: ChatReplyRequest) -> ChatReplyResponse:
    settings = load_chat_settings()
    memory_context = await fetch_memory_context(request, settings.memory_service_url)
    reply_text = await build_reply(request, memory_context)
    await store_conversation_turn(request, reply_text, settings.memory_service_url)
    return ChatReplyResponse(reply_text=reply_text)


def main() -> None:
    uvicorn.run("companion_bot.services.chat:app", host="127.0.0.1", port=8002)


if __name__ == "__main__":
    main()
