# Telegram HTTP REST Multiservice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram long-polling gateway backed by separate HTTP REST chat and memory services.

**Architecture:** The codebase will contain a small Python package named `companion_bot`. `telegram_gateway` owns Telegram integration, `services.chat` owns reply orchestration, and `services.memory` owns the memory REST API. Local services communicate with HTTP REST using typed request and response models.

**Tech Stack:** Python, FastAPI, Uvicorn, httpx, python-telegram-bot, pytest, pytest-asyncio, respx.

## Global Constraints

- Run a Telegram bot through long polling.
- Keep Telegram-specific code isolated in an edge gateway service.
- Route user messages through a chat service over HTTP REST.
- Keep memory access behind a separate memory service API.
- Provide a warm placeholder response while leaving the chat implementation replaceable.
- No production webhook deployment in this version.
- No durable database storage in this version.
- No real LLM integration in this version.
- No full memory extraction or summarization pipeline in this version.
- No authentication between local services in this version.
- `TELEGRAM_BOT_TOKEN` is required by `telegram-gateway`.
- `CHAT_SERVICE_URL` defaults to `http://127.0.0.1:8002`.
- `MEMORY_SERVICE_URL` defaults to `http://127.0.0.1:8001`.

---

## File Structure

- Create `pyproject.toml`: Python packaging, runtime dependencies, test dependencies, pytest settings.
- Create `README.md`: local setup and three-service run commands.
- Create `companion_bot/__init__.py`: package marker.
- Create `companion_bot/config.py`: environment parsing for gateway and chat service settings.
- Create `companion_bot/http.py`: shared HTTP timeout constant and helper for normalizing service URLs.
- Create `companion_bot/services/__init__.py`: service package marker.
- Create `companion_bot/services/memory.py`: FastAPI memory-service app and module entrypoint.
- Create `companion_bot/services/chat.py`: FastAPI chat-service app, memory client, placeholder reply logic, and module entrypoint.
- Create `companion_bot/telegram_gateway.py`: Telegram long-polling app, handlers, chat-service client, and module entrypoint.
- Create `tests/test_config.py`: configuration tests.
- Create `tests/test_memory_service.py`: memory-service API tests.
- Create `tests/test_chat_service.py`: chat-service API and memory fallback tests.
- Create `tests/test_telegram_gateway.py`: gateway handler tests with fake Telegram objects and mocked HTTP.

---

### Task 1: Project Scaffold And Configuration

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `companion_bot/__init__.py`
- Create: `companion_bot/config.py`
- Create: `companion_bot/http.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `companion_bot.config.GatewaySettings`
- Produces: `companion_bot.config.ChatSettings`
- Produces: `companion_bot.config.load_gateway_settings() -> GatewaySettings`
- Produces: `companion_bot.config.load_chat_settings() -> ChatSettings`
- Produces: `companion_bot.http.normalize_base_url(value: str) -> str`
- Produces: `companion_bot.http.DEFAULT_HTTP_TIMEOUT_SECONDS: float`

- [ ] **Step 1: Write failing configuration tests**

Create `tests/test_config.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`

Expected: FAIL during import because `companion_bot.config` does not exist.

- [ ] **Step 3: Add package metadata and dependencies**

Create `pyproject.toml`:

```toml
[project]
name = "companion-bot"
version = "0.1.0"
description = "Emotionally supportive companion chatbot services."
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111,<1.0",
    "httpx>=0.27,<1.0",
    "python-telegram-bot>=21,<22",
    "uvicorn[standard]>=0.30,<1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8,<9",
    "pytest-asyncio>=0.23,<1.0",
    "respx>=0.21,<1.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 4: Add configuration implementation**

Create `companion_bot/__init__.py`:

```python
"""Companion bot service package."""
```

Create `companion_bot/http.py`:

```python
DEFAULT_HTTP_TIMEOUT_SECONDS = 5.0


def normalize_base_url(value: str) -> str:
    return value.rstrip("/")
```

Create `companion_bot/config.py`:

```python
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
```

- [ ] **Step 5: Add initial README**

Create `README.md`:

```markdown
# Companion Bot

Emotionally supportive companion chatbot with Telegram as the first interaction channel.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run Services

Start each service in a separate terminal.

```bash
python -m companion_bot.services.memory
python -m companion_bot.services.chat
TELEGRAM_BOT_TOKEN=your-token python -m companion_bot.telegram_gateway
```

Default local service URLs:

- memory-service: `http://127.0.0.1:8001`
- chat-service: `http://127.0.0.1:8002`

Optional environment variables:

- `CHAT_SERVICE_URL`
- `MEMORY_SERVICE_URL`
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`

Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml README.md companion_bot/__init__.py companion_bot/config.py companion_bot/http.py tests/test_config.py
git commit -m "chore: scaffold companion bot package"
```

---

### Task 2: Memory Service

**Files:**
- Create: `companion_bot/services/__init__.py`
- Create: `companion_bot/services/memory.py`
- Create: `tests/test_memory_service.py`

**Interfaces:**
- Consumes: FastAPI from project dependencies.
- Produces: `companion_bot.services.memory.app`
- Produces: `companion_bot.services.memory.MemoryRecord`
- Produces: `companion_bot.services.memory.CreateMemoryRequest`
- Produces: `GET /v1/users/{user_id}/memories`
- Produces: `POST /v1/users/{user_id}/memories`

- [ ] **Step 1: Write failing memory-service tests**

Create `tests/test_memory_service.py`:

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

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_memory_service.py -v`

Expected: FAIL during import because `companion_bot.services.memory` does not exist.

- [ ] **Step 3: Implement memory service**

Create `companion_bot/services/__init__.py`:

```python
"""HTTP services for the companion bot."""
```

Create `companion_bot/services/memory.py`:

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

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_memory_service.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add companion_bot/services/__init__.py companion_bot/services/memory.py tests/test_memory_service.py
git commit -m "feat: add memory service"
```

---

### Task 3: Chat Service

**Files:**
- Create: `companion_bot/services/chat.py`
- Create: `tests/test_chat_service.py`

**Interfaces:**
- Consumes: `companion_bot.config.load_chat_settings() -> ChatSettings`
- Consumes: `companion_bot.http.DEFAULT_HTTP_TIMEOUT_SECONDS`
- Produces: `companion_bot.services.chat.app`
- Produces: `POST /v1/chat/reply`
- Produces: request model with `user_id: str`, `channel: str`, `message_text: str`
- Produces: response model with `reply_text: str`

- [ ] **Step 1: Write failing chat-service tests**

Create `tests/test_chat_service.py`:

```python
import httpx
import respx
from fastapi.testclient import TestClient

from companion_bot.services.chat import app


@respx.mock
def test_chat_reply_reads_and_writes_memory(monkeypatch):
    monkeypatch.setenv("MEMORY_SERVICE_URL", "http://memory.test")
    respx.get("http://memory.test/v1/users/telegram:123/memories").mock(
        return_value=httpx.Response(
            200,
            json={
                "user_id": "telegram:123",
                "memories": [
                    {
                        "kind": "preference",
                        "content": "User likes gentle check-ins.",
                        "source": "test",
                    }
                ],
            },
        )
    )
    post_route = respx.post("http://memory.test/v1/users/telegram:123/memories").mock(
        return_value=httpx.Response(200, json={"stored": True})
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/reply",
            json={
                "user_id": "telegram:123",
                "channel": "telegram",
                "message_text": "I had a hard day.",
            },
        )

    assert response.status_code == 200
    assert "I'm here with you" in response.json()["reply_text"]
    assert post_route.called


@respx.mock
def test_chat_reply_continues_when_memory_service_fails(monkeypatch):
    monkeypatch.setenv("MEMORY_SERVICE_URL", "http://memory.test")
    respx.get("http://memory.test/v1/users/telegram:123/memories").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"})
    )
    respx.post("http://memory.test/v1/users/telegram:123/memories").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"})
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/reply",
            json={
                "user_id": "telegram:123",
                "channel": "telegram",
                "message_text": "I feel overwhelmed.",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "reply_text": "I'm here with you. It sounds like this moment feels heavy, and you do not have to hold it alone."
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chat_service.py -v`

Expected: FAIL during import because `companion_bot.services.chat` does not exist.

- [ ] **Step 3: Implement chat service**

Create `companion_bot/services/chat.py`:

```python
import logging

from fastapi import FastAPI
import httpx
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

    return MemoriesResponse.model_validate(response.json()).memories


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


def build_placeholder_reply(
    request: ChatReplyRequest, memories: list[MemoryRecord]
) -> str:
    if memories:
        return (
            "I'm here with you. I remember a little context from before, "
            "and I want to stay gentle with what you are carrying right now."
        )

    return (
        "I'm here with you. It sounds like this moment feels heavy, "
        "and you do not have to hold it alone."
    )


@app.post("/v1/chat/reply", response_model=ChatReplyResponse)
async def reply(request: ChatReplyRequest) -> ChatReplyResponse:
    settings = load_chat_settings()
    memories = await fetch_memories(request.user_id, settings.memory_service_url)
    reply_text = build_placeholder_reply(request, memories)
    await store_interaction_note(request.user_id, settings.memory_service_url)
    return ChatReplyResponse(reply_text=reply_text)


def main() -> None:
    uvicorn.run("companion_bot.services.chat:app", host="127.0.0.1", port=8002)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_chat_service.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add companion_bot/services/chat.py tests/test_chat_service.py
git commit -m "feat: add chat service"
```

---

### Task 4: Telegram Gateway

**Files:**
- Create: `companion_bot/telegram_gateway.py`
- Create: `tests/test_telegram_gateway.py`

**Interfaces:**
- Consumes: `companion_bot.config.load_gateway_settings() -> GatewaySettings`
- Consumes: `companion_bot.http.DEFAULT_HTTP_TIMEOUT_SECONDS`
- Produces: `companion_bot.telegram_gateway.fetch_chat_reply(user_id: str, message_text: str, chat_service_url: str) -> str`
- Produces: `companion_bot.telegram_gateway.handle_start(update, context) -> None`
- Produces: `companion_bot.telegram_gateway.handle_text_message(update, context) -> None`
- Produces: `companion_bot.telegram_gateway.handle_unsupported_message(update, context) -> None`
- Produces: `companion_bot.telegram_gateway.build_application(token: str) -> telegram.ext.Application`

- [ ] **Step 1: Write failing Telegram gateway tests**

Create `tests/test_telegram_gateway.py`:

```python
from dataclasses import dataclass, field

import httpx
import pytest
import respx

from companion_bot.telegram_gateway import (
    fetch_chat_reply,
    handle_start,
    handle_text_message,
    handle_unsupported_message,
)


@dataclass
class FakeUser:
    id: int


@dataclass
class FakeMessage:
    text: str | None = None
    replies: list[str] = field(default_factory=list)

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


@dataclass
class FakeUpdate:
    effective_user: FakeUser
    message: FakeMessage


@dataclass
class FakeBotDataContext:
    bot_data: dict[str, str]


@respx.mock
@pytest.mark.asyncio
async def test_fetch_chat_reply_calls_chat_service():
    respx.post("http://chat.test/v1/chat/reply").mock(
        return_value=httpx.Response(200, json={"reply_text": "warm reply"})
    )

    reply = await fetch_chat_reply(
        user_id="telegram:123",
        message_text="hello",
        chat_service_url="http://chat.test",
    )

    assert reply == "warm reply"


@pytest.mark.asyncio
async def test_handle_start_replies_with_welcome_message():
    update = FakeUpdate(effective_user=FakeUser(id=123), message=FakeMessage())
    context = FakeBotDataContext(bot_data={"chat_service_url": "http://chat.test"})

    await handle_start(update, context)

    assert update.message.replies == [
        "Hi, I'm here with you. Send me a message whenever you want company."
    ]


@respx.mock
@pytest.mark.asyncio
async def test_handle_text_message_forwards_to_chat_service():
    respx.post("http://chat.test/v1/chat/reply").mock(
        return_value=httpx.Response(200, json={"reply_text": "I'm listening."})
    )
    update = FakeUpdate(
        effective_user=FakeUser(id=123),
        message=FakeMessage(text="I feel sad."),
    )
    context = FakeBotDataContext(bot_data={"chat_service_url": "http://chat.test"})

    await handle_text_message(update, context)

    assert update.message.replies == ["I'm listening."]


@respx.mock
@pytest.mark.asyncio
async def test_handle_text_message_uses_fallback_when_chat_service_fails():
    respx.post("http://chat.test/v1/chat/reply").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"})
    )
    update = FakeUpdate(
        effective_user=FakeUser(id=123),
        message=FakeMessage(text="Are you there?"),
    )
    context = FakeBotDataContext(bot_data={"chat_service_url": "http://chat.test"})

    await handle_text_message(update, context)

    assert update.message.replies == [
        "I'm here, but I had trouble thinking clearly for a moment. Please send that again."
    ]


@pytest.mark.asyncio
async def test_handle_unsupported_message_gently_declines():
    update = FakeUpdate(effective_user=FakeUser(id=123), message=FakeMessage())
    context = FakeBotDataContext(bot_data={"chat_service_url": "http://chat.test"})

    await handle_unsupported_message(update, context)

    assert update.message.replies == [
        "I can only read text right now, but you can send me a message in words."
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_telegram_gateway.py -v`

Expected: FAIL during import because `companion_bot.telegram_gateway` does not exist.

- [ ] **Step 3: Implement Telegram gateway**

Create `companion_bot/telegram_gateway.py`:

```python
import logging
from typing import Any

import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from companion_bot.config import load_gateway_settings
from companion_bot.http import DEFAULT_HTTP_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

START_REPLY = "Hi, I'm here with you. Send me a message whenever you want company."
CHAT_FALLBACK_REPLY = (
    "I'm here, but I had trouble thinking clearly for a moment. Please send that again."
)
UNSUPPORTED_MESSAGE_REPLY = (
    "I can only read text right now, but you can send me a message in words."
)


async def fetch_chat_reply(
    user_id: str, message_text: str, chat_service_url: str
) -> str:
    async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{chat_service_url}/v1/chat/reply",
            json={
                "user_id": user_id,
                "channel": "telegram",
                "message_text": message_text,
            },
        )
        response.raise_for_status()
        return str(response.json()["reply_text"])


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(START_REPLY)


async def handle_text_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE | Any
) -> None:
    if update.message is None or update.effective_user is None:
        return

    chat_service_url = context.bot_data["chat_service_url"]
    user_id = f"telegram:{update.effective_user.id}"
    message_text = update.message.text or ""

    try:
        reply_text = await fetch_chat_reply(user_id, message_text, chat_service_url)
    except httpx.HTTPError:
        logger.exception("Failed to fetch chat reply for user_id=%s", user_id)
        reply_text = CHAT_FALLBACK_REPLY

    await update.message.reply_text(reply_text)


async def handle_unsupported_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.message is None:
        return
    await update.message.reply_text(UNSUPPORTED_MESSAGE_REPLY)


def build_application(token: str) -> Application:
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )
    application.add_handler(MessageHandler(~filters.TEXT, handle_unsupported_message))
    return application


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_gateway_settings()
    application = build_application(settings.telegram_bot_token)
    application.bot_data["chat_service_url"] = settings.chat_service_url
    logger.info("Starting telegram-gateway with chat_service_url=%s", settings.chat_service_url)
    application.run_polling()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_telegram_gateway.py -v`

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add companion_bot/telegram_gateway.py tests/test_telegram_gateway.py
git commit -m "feat: add telegram gateway"
```

---

### Task 5: Full Verification And Documentation Pass

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: all interfaces from Tasks 1-4.
- Produces: verified local commands and service documentation.

- [ ] **Step 1: Update README with API examples**

Modify `README.md` to:

```markdown
# Companion Bot

Emotionally supportive companion chatbot with Telegram as the first interaction channel.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run Services

Start each service in a separate terminal.

```bash
python -m companion_bot.services.memory
```

```bash
python -m companion_bot.services.chat
```

```bash
TELEGRAM_BOT_TOKEN=your-token python -m companion_bot.telegram_gateway
```

Default local service URLs:

- memory-service: `http://127.0.0.1:8001`
- chat-service: `http://127.0.0.1:8002`

Optional environment variables:

- `CHAT_SERVICE_URL`
- `MEMORY_SERVICE_URL`

## HTTP APIs

Chat reply:

```bash
curl -X POST http://127.0.0.1:8002/v1/chat/reply \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"telegram:123","channel":"telegram","message_text":"I had a hard day."}'
```

Read memories:

```bash
curl http://127.0.0.1:8001/v1/users/telegram:123/memories
```

Store memory:

```bash
curl -X POST http://127.0.0.1:8001/v1/users/telegram:123/memories \
  -H 'Content-Type: application/json' \
  -d '{"kind":"interaction_note","content":"User sent a message through Telegram.","source":"chat-service"}'
```
```

- [ ] **Step 2: Run full test suite**

Run: `pytest -v`

Expected: all tests pass.

- [ ] **Step 3: Check git status**

Run: `git status --short`

Expected: only intentional files are modified or untracked before the final commit.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document local service usage"
```

