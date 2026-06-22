# Memory Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone FastAPI memory service with in-process storage and GET/POST memory APIs.

**Architecture:** The service lives in `companion_bot.services.memory` and owns its own FastAPI app, request/response models, and ephemeral store. The package marker in `companion_bot.services.__init__` keeps the service namespace importable, while tests exercise the REST contract through `TestClient` rather than internal helpers.

**Tech Stack:** Python, FastAPI, Pydantic, Uvicorn, pytest.

## Global Constraints

- Memory data is stored in process memory for this version.
- `GET /v1/users/{user_id}/memories` returns an empty list for users with no memories.
- `POST /v1/users/{user_id}/memories` accepts `kind`, `content`, and `source`.
- No durable database storage in this version.
- No authentication between local services in this version.

---

### Task 1: Lock The REST Contract In Tests

**Files:**
- Create: `tests/test_memory_service.py`

**Interfaces:**
- Produces: `tests.test_memory_service.test_get_memories_returns_empty_list_for_new_user`
- Produces: `tests.test_memory_service.test_post_memory_stores_record_for_user`

- [ ] **Step 1: Write the failing tests**

```python
from fastapi.testclient import TestClient

from companion_bot.services.memory import app


def test_get_memories_returns_empty_list_for_new_user():
    with TestClient(app) as client:
        response = client.get("/v1/users/telegram:123/memories")

    assert response.status_code == 200
    assert response.json() == {"user_id": "telegram:123", "memories": []}


def test_post_memory_stores_record_for_user():
    with TestClient(app) as client:
        create_response = client.post(
            "/v1/users/telegram:123/memories",
            json={
                "kind": "interaction_note",
                "content": "User sent a message through Telegram.",
                "source": "chat-service",
            },
        )
        get_response = client.get("/v1/users/telegram:123/memories")

    assert create_response.status_code == 200
    assert create_response.json() == {"stored": True}
    assert get_response.status_code == 200
    assert get_response.json() == {
        "user_id": "telegram:123",
        "memories": [
            {
                "kind": "interaction_note",
                "content": "User sent a message through Telegram.",
                "source": "chat-service",
            }
        ],
    }
```

- [ ] **Step 2: Run the test file and confirm import failure**

Run: `pytest tests/test_memory_service.py -v`

Expected: FAIL during import because `companion_bot.services.memory` does not exist yet.

---

### Task 2: Implement The Memory Service

**Files:**
- Create: `companion_bot/services/__init__.py`
- Create: `companion_bot/services/memory.py`

**Interfaces:**
- Produces: `companion_bot.services.memory.app`
- Produces: `companion_bot.services.memory.MemoryRecord`
- Produces: `companion_bot.services.memory.CreateMemoryRequest`

- [ ] **Step 1: Add the package marker**

```python
"""HTTP services for the companion bot."""
```

- [ ] **Step 2: Add the FastAPI app and in-memory store**

```python
from collections import defaultdict

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


app = FastAPI(title="companion-memory-service")
_memory_store: dict[str, list[MemoryRecord]] = defaultdict(list)


@app.on_event("startup")
async def clear_memory_store() -> None:
    _memory_store.clear()


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
```

- [ ] **Step 3: Run the focused test file and confirm success**

Run: `pytest tests/test_memory_service.py -v`

Expected: `2 passed`

- [ ] **Step 4: Commit**

```bash
git add companion_bot/services/__init__.py companion_bot/services/memory.py tests/test_memory_service.py docs/superpowers/plans/2026-06-22-task-2-memory-service.md
git commit -m "feat: add memory service"
```

---

## Self-Review

**1. Spec coverage:** The two REST endpoints, in-process storage, and empty-list behavior are each covered by the tests and implementation task.

**2. Placeholder scan:** No placeholders remain in the plan text or code blocks.

**3. Type consistency:** The request and response models are named consistently across tests, implementation, and the public module interface.
