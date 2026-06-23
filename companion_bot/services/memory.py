from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

from companion_bot.memory import AgentMemory, ConversationTurn


class CreateMemoryRequest(BaseModel):
    kind: str
    content: str
    source: str


class MemoryRecord(BaseModel):
    kind: str
    content: str
    source: str


class MemoriesResponse(BaseModel):
    user_id: str
    memories: list[MemoryRecord]


class StoreMemoryResponse(BaseModel):
    stored: bool


class MemoryContextRequest(BaseModel):
    channel: str
    message_text: str
    message_timestamp: str | None = None


class MemoryContextResponse(BaseModel):
    user_id: str
    context: dict[str, Any]


class ConversationTurnRequest(BaseModel):
    channel: str
    message_text: str
    message_timestamp: str | None = None
    assistant_reply: str | None = None


class ConversationTurnResponse(BaseModel):
    updated: bool
    memory_update: dict[str, Any]


_memory_store: dict[str, list[MemoryRecord]] = defaultdict(list)
_agent_memories: dict[str, AgentMemory] = defaultdict(AgentMemory)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _memory_store.clear()
    _agent_memories.clear()
    yield


app = FastAPI(title="companion-memory-service", lifespan=lifespan)


@app.get("/v1/users/{user_id}/memories", response_model=MemoriesResponse)
async def get_memories(user_id: str) -> MemoriesResponse:
    return MemoriesResponse(user_id=user_id, memories=list(_memory_store[user_id]))


@app.post("/v1/users/{user_id}/memories", response_model=StoreMemoryResponse)
async def store_memory(
    user_id: str, request: CreateMemoryRequest
) -> StoreMemoryResponse:
    _memory_store[user_id].append(MemoryRecord(**request.model_dump()))
    return StoreMemoryResponse(stored=True)


def _conversation_turn(
    user_id: str, request: MemoryContextRequest | ConversationTurnRequest
) -> ConversationTurn:
    return ConversationTurn(
        user_id=user_id,
        channel=request.channel,
        message_text=request.message_text,
        message_timestamp=request.message_timestamp,
        assistant_reply=getattr(request, "assistant_reply", None),
    )


@app.post("/v1/users/{user_id}/memory/context", response_model=MemoryContextResponse)
async def get_memory_context(
    user_id: str, request: MemoryContextRequest
) -> MemoryContextResponse:
    memory = _agent_memories[user_id]
    return MemoryContextResponse(
        user_id=user_id,
        context=memory.retrieve_context(_conversation_turn(user_id, request)),
    )


@app.post("/v1/users/{user_id}/memory/turns", response_model=ConversationTurnResponse)
async def store_conversation_turn(
    user_id: str, request: ConversationTurnRequest
) -> ConversationTurnResponse:
    memory = _agent_memories[user_id]
    update = memory.update(_conversation_turn(user_id, request))
    return ConversationTurnResponse(updated=True, memory_update=update)


def main() -> None:
    uvicorn.run("companion_bot.services.memory:app", host="127.0.0.1", port=8001)


if __name__ == "__main__":
    main()
