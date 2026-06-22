import logging

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


class MemoryRecord(BaseModel):
    kind: str
    content: str
    source: str


class MemoriesResponse(BaseModel):
    user_id: str
    memories: list[MemoryRecord]


app = FastAPI(title="companion-chat-service")


async def fetch_memories(user_id: str, memory_service_url: str) -> list[MemoryRecord]:
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{memory_service_url}/v1/users/{user_id}/memories"
            )
            response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Failed to fetch memories for user_id=%s", user_id)
        return []

    try:
        return MemoriesResponse.model_validate(response.json()).memories
    except (ValueError, TypeError):
        logger.exception("Invalid memory payload for user_id=%s", user_id)
        return []


async def store_interaction_note(user_id: str, memory_service_url: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{memory_service_url}/v1/users/{user_id}/memories",
                json={
                    "kind": "interaction_note",
                    "content": "User sent a message through a chat channel.",
                    "source": "chat-service",
                },
            )
            response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Failed to store interaction note for user_id=%s", user_id)


async def build_reply(request: ChatReplyRequest) -> str:
    try:
        settings = load_llm_settings()
        return await generate_chat_reply(
            messages=[
                ChatMessage(role="system", content=SYSTEM_PROMPT),
                ChatMessage(role="user", content=request.message_text),
            ],
            settings=settings,
        )
    except (RuntimeError, LLMClientError):
        logger.exception(
            "Failed to generate LLM reply for user_id=%s channel=%s",
            request.user_id,
            request.channel,
        )
        return LLM_FALLBACK_REPLY


@app.post("/v1/chat/reply", response_model=ChatReplyResponse)
async def reply(request: ChatReplyRequest) -> ChatReplyResponse:
    settings = load_chat_settings()
    await fetch_memories(request.user_id, settings.memory_service_url)
    reply_text = await build_reply(request)
    await store_interaction_note(request.user_id, settings.memory_service_url)
    return ChatReplyResponse(reply_text=reply_text)


def main() -> None:
    uvicorn.run("companion_bot.services.chat:app", host="127.0.0.1", port=8002)


if __name__ == "__main__":
    main()
