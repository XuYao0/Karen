from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn


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


_memory_store: dict[str, list[MemoryRecord]] = defaultdict(list)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _memory_store.clear()
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


def main() -> None:
    uvicorn.run("companion_bot.services.memory:app", host="127.0.0.1", port=8001)


if __name__ == "__main__":
    main()
