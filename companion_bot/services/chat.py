import logging

import httpx
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

from companion_bot.config import load_chat_settings
from companion_bot.http import DEFAULT_HTTP_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class ChatReplyRequest(BaseModel):
    user_id: str
    channel: str
    message_text: str


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
                    "content": "User sent a message through Telegram.",
                    "source": "chat-service",
                },
            )
            response.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Failed to store interaction note for user_id=%s", user_id)


def build_reply(request: ChatReplyRequest, memories: list[MemoryRecord]) -> str:
    if memories:
        return (
            "I'm here with you. I remember a little context from before, and I want "
            "to stay gentle with what you are carrying right now."
        )

    return (
        "I'm here with you. It sounds like this moment feels heavy, and you do "
        "not have to hold it alone."
    )


@app.post("/v1/chat/reply", response_model=ChatReplyResponse)
async def reply(request: ChatReplyRequest) -> ChatReplyResponse:
    settings = load_chat_settings()
    memories = await fetch_memories(request.user_id, settings.memory_service_url)
    reply_text = build_reply(request, memories)
    await store_interaction_note(request.user_id, settings.memory_service_url)
    return ChatReplyResponse(reply_text=reply_text)


def main() -> None:
    uvicorn.run("companion_bot.services.chat:app", host="127.0.0.1", port=8002)


if __name__ == "__main__":
    main()
