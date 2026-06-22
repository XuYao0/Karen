# DeepSeek LLM Connectivity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the local chat placeholder with a DeepSeek-backed LLM reply path while preserving warm fallbacks and the existing Telegram -> chat-service -> memory-service boundaries.

**Architecture:** Add a small OpenAI-compatible LLM client module with DeepSeek defaults and provider-specific request fields kept inside the client/config layer. Extend chat-service to call that client with only the latest incoming user message, and extend telegram-gateway to pass Telegram message time as a UTC ISO 8601 `message_timestamp`.

**Tech Stack:** Python 3.11+, FastAPI, httpx, python-telegram-bot, pytest, pytest-asyncio, respx.

## Global Constraints

- DeepSeek API key must be read from `DEEPSEEK_API_KEY`.
- `LLM_PROVIDER` defaults to `deepseek`.
- First version only supports `LLM_PROVIDER=deepseek`.
- `LLM_BASE_URL` defaults to `https://api.deepseek.com`.
- `LLM_MODEL` defaults to `deepseek-v4-pro`.
- `LLM_REASONING_EFFORT` defaults to `high`.
- `LLM_THINKING_ENABLED` defaults to `true`.
- DeepSeek request body must include OpenAI-compatible `messages`.
- DeepSeek request body must include `"thinking": {"type": "enabled"}` when thinking is enabled.
- DeepSeek request body must include `"reasoning_effort": "high"` by default.
- DeepSeek request body must include `"stream": false`.
- Only the latest user message is sent to DeepSeek in this version.
- Do not send memory records or conversation history to DeepSeek in this version.
- Telegram gateway must pass Telegram message time to chat-service as UTC ISO 8601 `message_timestamp`.
- No user local timezone inference in this version.
- LLM failure must return this user-facing fallback: `我在认真想怎么回应你，但刚刚有点卡住了。你可以再发我一次，我会继续陪你。`
- Telegram gateway must not call DeepSeek directly.
- Provider-specific request fields must stay out of Telegram gateway and chat route orchestration.

---

## File Structure

- Modify `companion_bot/config.py`: add `LLMSettings` and `load_llm_settings()`.
- Create `companion_bot/llm.py`: DeepSeek/OpenAI-compatible async client and response parsing.
- Modify `companion_bot/services/chat.py`: add `message_timestamp`, call LLM client, keep memory best-effort, use LLM fallback.
- Modify `companion_bot/telegram_gateway.py`: include UTC ISO 8601 timestamp in chat-service request.
- Modify `README.md`: document DeepSeek environment variables and LLM behavior.
- Modify `tests/test_config.py`: config coverage for LLM settings.
- Create `tests/test_llm.py`: DeepSeek client request/response/failure tests.
- Modify `tests/test_chat_service.py`: chat-service LLM success/fallback and latest-message-only tests.
- Modify `tests/test_telegram_gateway.py`: timestamp forwarding test.

---

### Task 1: LLM Configuration

**Files:**
- Modify: `companion_bot/config.py`
- Modify: `tests/test_config.py`

**Interfaces:**
- Produces: `companion_bot.config.LLMSettings`
- Produces: `companion_bot.config.load_llm_settings() -> LLMSettings`
- Produces fields:
  - `provider: str`
  - `api_key: str`
  - `base_url: str`
  - `model: str`
  - `reasoning_effort: str`
  - `thinking_enabled: bool`

- [ ] **Step 1: Write failing LLM configuration tests**

Append to `tests/test_config.py`:

```python
import pytest

from companion_bot.config import LLMSettings, load_llm_settings


def test_load_llm_settings_requires_deepseek_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        load_llm_settings()


def test_load_llm_settings_uses_deepseek_defaults(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("LLM_THINKING_ENABLED", raising=False)

    settings = load_llm_settings()

    assert settings == LLMSettings(
        provider="deepseek",
        api_key="deepseek-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-pro",
        reasoning_effort="high",
        thinking_enabled=True,
    )


def test_load_llm_settings_normalizes_base_url(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com/")

    settings = load_llm_settings()

    assert settings.base_url == "https://api.deepseek.com"


def test_load_llm_settings_rejects_unsupported_provider(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    with pytest.raises(RuntimeError, match="Unsupported LLM_PROVIDER"):
        load_llm_settings()


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("0", False),
        ("no", False),
    ],
)
def test_load_llm_settings_parses_thinking_enabled(
    monkeypatch, raw_value, expected
):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("LLM_THINKING_ENABLED", raw_value)

    settings = load_llm_settings()

    assert settings.thinking_enabled is expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_config.py -v
```

Expected: FAIL because `LLMSettings` and `load_llm_settings` do not exist.

- [ ] **Step 3: Implement LLM settings**

Modify `companion_bot/config.py`:

```python
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

    thinking_raw = os.getenv("LLM_THINKING_ENABLED", "true")

    return LLMSettings(
        provider=provider,
        api_key=api_key,
        base_url=normalize_base_url(os.getenv("LLM_BASE_URL", DEFAULT_LLM_BASE_URL)),
        model=os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL),
        reasoning_effort=os.getenv(
            "LLM_REASONING_EFFORT", DEFAULT_LLM_REASONING_EFFORT
        ),
        thinking_enabled=_parse_bool(thinking_raw),
    )
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_config.py -v
```

Expected: all config tests pass.

- [ ] **Step 5: Commit**

```bash
git add companion_bot/config.py tests/test_config.py
git commit -m "feat: add llm settings"
```

---

### Task 2: DeepSeek LLM Client

**Files:**
- Create: `companion_bot/llm.py`
- Create: `tests/test_llm.py`

**Interfaces:**
- Consumes: `companion_bot.config.LLMSettings`
- Consumes: `companion_bot.http.DEFAULT_HTTP_TIMEOUT_SECONDS`
- Produces: `companion_bot.llm.ChatMessage`
- Produces: `companion_bot.llm.LLMClientError`
- Produces: `companion_bot.llm.generate_chat_reply(messages: list[ChatMessage], settings: LLMSettings) -> str`

- [ ] **Step 1: Write failing DeepSeek client tests**

Create `tests/test_llm.py`:

```python
import httpx
import pytest
import respx

from companion_bot.config import LLMSettings
from companion_bot.llm import ChatMessage, LLMClientError, generate_chat_reply


def make_settings(**overrides):
    values = {
        "provider": "deepseek",
        "api_key": "deepseek-key",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-pro",
        "reasoning_effort": "high",
        "thinking_enabled": True,
    }
    values.update(overrides)
    return LLMSettings(**values)


@respx.mock
@pytest.mark.asyncio
async def test_generate_chat_reply_calls_deepseek_with_provider_specific_body():
    route = respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "你好，我在。",
                        }
                    }
                ]
            },
        )
    )

    reply = await generate_chat_reply(
        messages=[
            ChatMessage(role="system", content="You are Karen."),
            ChatMessage(role="user", content="你好"),
        ],
        settings=make_settings(),
    )

    assert reply == "你好，我在。"
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer deepseek-key"
    assert request.headers["content-type"] == "application/json"
    assert request.json() == {
        "model": "deepseek-v4-pro",
        "messages": [
            {"role": "system", "content": "You are Karen."},
            {"role": "user", "content": "你好"},
        ],
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
        "stream": False,
    }


@respx.mock
@pytest.mark.asyncio
async def test_generate_chat_reply_omits_thinking_when_disabled():
    route = respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "plain reply"}}]},
        )
    )

    reply = await generate_chat_reply(
        messages=[ChatMessage(role="user", content="hello")],
        settings=make_settings(thinking_enabled=False),
    )

    assert reply == "plain reply"
    assert "thinking" not in route.calls.last.request.json()


@respx.mock
@pytest.mark.asyncio
async def test_generate_chat_reply_raises_on_http_error():
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"})
    )

    with pytest.raises(LLMClientError, match="DeepSeek request failed"):
        await generate_chat_reply(
            messages=[ChatMessage(role="user", content="hello")],
            settings=make_settings(),
        )


@respx.mock
@pytest.mark.asyncio
async def test_generate_chat_reply_raises_on_invalid_response_shape():
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": []})
    )

    with pytest.raises(LLMClientError, match="Invalid DeepSeek response"):
        await generate_chat_reply(
            messages=[ChatMessage(role="user", content="hello")],
            settings=make_settings(),
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_llm.py -v
```

Expected: FAIL because `companion_bot.llm` does not exist.

- [ ] **Step 3: Implement DeepSeek client**

Create `companion_bot/llm.py`:

```python
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
            {"role": message.role, "content": message.content}
            for message in messages
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
    except httpx.HTTPError as exc:
        raise LLMClientError("DeepSeek request failed") from exc

    return _parse_deepseek_reply(response.json())
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_llm.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add companion_bot/llm.py tests/test_llm.py
git commit -m "feat: add deepseek llm client"
```

---

### Task 3: Chat Service LLM Reply Path

**Files:**
- Modify: `companion_bot/services/chat.py`
- Modify: `tests/test_chat_service.py`

**Interfaces:**
- Consumes: `companion_bot.config.load_llm_settings() -> LLMSettings`
- Consumes: `companion_bot.llm.ChatMessage`
- Consumes: `companion_bot.llm.LLMClientError`
- Consumes: `companion_bot.llm.generate_chat_reply(...) -> str`
- Produces: `ChatReplyRequest.message_timestamp: str | None`
- Produces fallback text: `我在认真想怎么回应你，但刚刚有点卡住了。你可以再发我一次，我会继续陪你。`

- [ ] **Step 1: Write failing chat-service LLM success test**

Modify `tests/test_chat_service.py`.

Add imports:

```python
from companion_bot.config import LLMSettings
```

Add test:

```python
@respx.mock
def test_chat_reply_uses_deepseek_latest_message_only(monkeypatch):
    monkeypatch.setenv("MEMORY_SERVICE_URL", "http://memory.test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    respx.get("http://memory.test/v1/users/telegram:123/memories").mock(
        return_value=httpx.Response(
            200,
            json={
                "user_id": "telegram:123",
                "memories": [
                    {
                        "kind": "preference",
                        "content": "This must not be sent to the LLM yet.",
                        "source": "test",
                    }
                ],
            },
        )
    )
    respx.post("http://memory.test/v1/users/telegram:123/memories").mock(
        return_value=httpx.Response(200, json={"stored": True})
    )
    deepseek_route = respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "你好，我听见你了。"}}]},
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/reply",
            json={
                "user_id": "telegram:123",
                "channel": "telegram",
                "message_text": "你好",
                "message_timestamp": "2026-06-22T06:46:00+00:00",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"reply_text": "你好，我听见你了。"}
    request_body = deepseek_route.calls.last.request.json()
    assert request_body["messages"] == [
        {
            "role": "system",
            "content": "You are Karen, a warm and emotionally present AI friend. Reply naturally and briefly.",
        },
        {"role": "user", "content": "你好"},
    ]
    assert "This must not be sent to the LLM yet." not in str(request_body)
```

- [ ] **Step 2: Write failing chat-service LLM fallback test**

Append to `tests/test_chat_service.py`:

```python
@respx.mock
def test_chat_reply_uses_transparent_fallback_when_deepseek_fails(monkeypatch):
    monkeypatch.setenv("MEMORY_SERVICE_URL", "http://memory.test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    respx.get("http://memory.test/v1/users/telegram:123/memories").mock(
        return_value=httpx.Response(200, json={"user_id": "telegram:123", "memories": []})
    )
    respx.post("http://memory.test/v1/users/telegram:123/memories").mock(
        return_value=httpx.Response(200, json={"stored": True})
    )
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"})
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/reply",
            json={
                "user_id": "telegram:123",
                "channel": "telegram",
                "message_text": "你好",
                "message_timestamp": "2026-06-22T06:46:00+00:00",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "reply_text": "我在认真想怎么回应你，但刚刚有点卡住了。你可以再发我一次，我会继续陪你。"
    }
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_chat_service.py -v
```

Expected: FAIL because chat-service still returns local placeholder and does not call DeepSeek.

- [ ] **Step 4: Implement chat-service LLM path**

Modify `companion_bot/services/chat.py`:

```python
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
```

- [ ] **Step 5: Update existing chat-service tests for new fallback behavior**

In `tests/test_chat_service.py`, existing tests that do not focus on DeepSeek must set `DEEPSEEK_API_KEY` and mock `https://api.deepseek.com/chat/completions`, or assert the LLM fallback when no key/provider is available.

For the existing memory failure test, prefer proving memory failure does not block LLM success:

```python
@respx.mock
def test_chat_reply_continues_when_memory_service_fails(monkeypatch):
    monkeypatch.setenv("MEMORY_SERVICE_URL", "http://memory.test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    respx.get("http://memory.test/v1/users/telegram:123/memories").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"})
    )
    respx.post("http://memory.test/v1/users/telegram:123/memories").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"})
    )
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "我会陪你慢慢来。"}}]},
        )
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
    assert response.json() == {"reply_text": "我会陪你慢慢来。"}
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_chat_service.py tests/test_llm.py -v
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```bash
git add companion_bot/services/chat.py tests/test_chat_service.py
git commit -m "feat: use llm replies in chat service"
```

---

### Task 4: Telegram UTC Timestamp Forwarding

**Files:**
- Modify: `companion_bot/telegram_gateway.py`
- Modify: `tests/test_telegram_gateway.py`

**Interfaces:**
- Consumes: `update.message.date`
- Produces: `message_timestamp` in chat-service request JSON

- [ ] **Step 1: Write failing timestamp forwarding test**

Modify `tests/test_telegram_gateway.py`.

Update imports:

```python
from datetime import datetime, timezone
```

Update `FakeMessage` to include `date`:

```python
@dataclass
class FakeMessage:
    text: str | None = None
    date: datetime | None = None
    replies: list[str] = field(default_factory=list)

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)
```

Add test:

```python
@respx.mock
@pytest.mark.asyncio
async def test_handle_text_message_forwards_utc_message_timestamp():
    route = respx.post("http://chat.test/v1/chat/reply").mock(
        return_value=httpx.Response(200, json={"reply_text": "I'm listening."})
    )
    update = FakeUpdate(
        effective_user=FakeUser(id=123),
        message=FakeMessage(
            text="你好",
            date=datetime(2026, 6, 22, 6, 46, tzinfo=timezone.utc),
        ),
    )
    context = FakeBotDataContext(bot_data={"chat_service_url": "http://chat.test"})

    await handle_text_message(update, context)

    assert route.calls.last.request.json()["message_timestamp"] == (
        "2026-06-22T06:46:00+00:00"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_telegram_gateway.py -v
```

Expected: FAIL because gateway does not send `message_timestamp`.

- [ ] **Step 3: Implement timestamp serialization**

Modify `companion_bot/telegram_gateway.py`:

```python
from datetime import timezone
import logging
from typing import Any
```

Add helper:

```python
def serialize_message_timestamp(update: Update) -> str | None:
    if update.message is None or update.message.date is None:
        return None
    return update.message.date.astimezone(timezone.utc).isoformat()
```

Modify `fetch_chat_reply` signature and body:

```python
async def fetch_chat_reply(
    user_id: str,
    message_text: str,
    chat_service_url: str,
    message_timestamp: str | None = None,
) -> str:
    payload = {
        "user_id": user_id,
        "channel": "telegram",
        "message_text": message_text,
    }
    if message_timestamp is not None:
        payload["message_timestamp"] = message_timestamp

    async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{chat_service_url}/v1/chat/reply",
            json=payload,
        )
        response.raise_for_status()
        return str(response.json()["reply_text"])
```

Modify `handle_text_message`:

```python
reply_text = await fetch_chat_reply(
    user_id=user_id,
    message_text=message_text,
    chat_service_url=chat_service_url,
    message_timestamp=serialize_message_timestamp(update),
)
```

- [ ] **Step 4: Update direct fetch test**

Existing `test_fetch_chat_reply_calls_chat_service` should assert the default payload remains compatible:

```python
@respx.mock
@pytest.mark.asyncio
async def test_fetch_chat_reply_calls_chat_service():
    route = respx.post("http://chat.test/v1/chat/reply").mock(
        return_value=httpx.Response(200, json={"reply_text": "warm reply"})
    )

    reply = await fetch_chat_reply(
        user_id="telegram:123",
        message_text="hello",
        chat_service_url="http://chat.test",
    )

    assert reply == "warm reply"
    assert route.calls.last.request.json() == {
        "user_id": "telegram:123",
        "channel": "telegram",
        "message_text": "hello",
    }
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_telegram_gateway.py -v
```

Expected: all gateway tests pass.

- [ ] **Step 6: Commit**

```bash
git add companion_bot/telegram_gateway.py tests/test_telegram_gateway.py
git commit -m "feat: forward telegram message timestamp"
```

---

### Task 5: Documentation And Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-22-deepseek-llm-connectivity-design.md` only if implementation intentionally differs from the spec.

**Interfaces:**
- Consumes: all interfaces from Tasks 1-4.
- Produces: documented DeepSeek local setup and smoke-test instructions.

- [ ] **Step 1: Update README with LLM configuration**

Modify `README.md` environment sections to include:

```markdown
Required environment variables:

- `TELEGRAM_BOT_TOKEN` only for `telegram-gateway`
- `DEEPSEEK_API_KEY` for real LLM replies in `chat-service`

Optional environment variables:

- `CHAT_SERVICE_URL`
- `MEMORY_SERVICE_URL`
- `LLM_PROVIDER` defaults to `deepseek`
- `LLM_BASE_URL` defaults to `https://api.deepseek.com`
- `LLM_MODEL` defaults to `deepseek-v4-pro`
- `LLM_REASONING_EFFORT` defaults to `high`
- `LLM_THINKING_ENABLED` defaults to `true`
```

Add local smoke example:

````markdown
## LLM Smoke Test

With `memory-service` and `chat-service` running:

```bash
curl -X POST http://127.0.0.1:8002/v1/chat/reply \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"telegram:123","channel":"telegram","message_text":"你好","message_timestamp":"2026-06-22T06:46:00+00:00"}'
```

If `DEEPSEEK_API_KEY` is configured for `chat-service`, the response should come from DeepSeek. If DeepSeek is unavailable, chat-service returns a warm fallback.
````

- [ ] **Step 2: Run full test suite**

Run:

```bash
.venv/bin/python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Optional real DeepSeek smoke test**

Only run when `DEEPSEEK_API_KEY` is available in the current shell and the user explicitly wants a network smoke:

```bash
curl -X POST http://127.0.0.1:8002/v1/chat/reply \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"telegram:manual-smoke","channel":"telegram","message_text":"你好，请简单回复一句。","message_timestamp":"2026-06-22T06:46:00+00:00"}'
```

Expected: JSON response with `reply_text`.

- [ ] **Step 4: Check git status**

Run:

```bash
git status --short
```

Expected: only intentional tracked files are modified or untracked before commit.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers/specs/2026-06-22-deepseek-llm-connectivity-design.md
git commit -m "docs: document deepseek llm setup"
```
