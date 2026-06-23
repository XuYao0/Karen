# AC Memory Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the online memory model from `~/friends/ac` into Karen, expose it through memory-service, and feed compact memory context into chat-service LLM calls.

**Architecture:** Add a pure domain module `companion_bot/memory.py` adapted from `ac.memory`, then wrap it with REST endpoints in `companion_bot/services/memory.py`. `companion_bot/services/chat.py` will fetch memory context before LLM generation and store the completed conversation turn after reply generation, while preserving graceful degradation when memory-service is unavailable.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, httpx, pytest, respx.

## Global Constraints

- Follow `AGENTS.md`: documentation first and Chinese project communication.
- Base implementation on `feature/deepseek-llm-connectivity` so LLM and timestamp plumbing remain available.
- Keep the current in-memory storage behavior; do not introduce a database.
- Preserve existing `/v1/users/{user_id}/memories` GET/POST compatibility.
- Memory context must only include information observed before the latest user message.
- Chat-service must still return a reply when memory-service fails.
- Do not log API keys or full provider secrets.

---

## File Structure

- Create `companion_bot/memory.py`: pure domain model adapted from `~/friends/ac/memory.py`, with Karen-specific `ConversationTurn`.
- Create `tests/test_memory_domain.py`: unit tests for context retrieval, update, and compression.
- Modify `companion_bot/services/memory.py`: add online memory store and context/update REST endpoints while preserving existing flat memory endpoints.
- Modify `tests/test_memory_service.py`: cover new endpoints and startup clearing behavior for both stores.
- Modify `companion_bot/services/chat.py`: add context fetch, context formatting, and turn update calls.
- Modify `tests/test_chat_service.py`: update mocks and assert LLM messages include memory context.
- Modify `README.md`: document new memory APIs and current in-memory limits.

---

### Task 1: Domain Memory Module

**Files:**
- Create: `companion_bot/memory.py`
- Create: `tests/test_memory_domain.py`

**Interfaces:**
- Produces: `ConversationTurn(user_id: str, channel: str, message_text: str, message_timestamp: str | None = None, assistant_reply: str | None = None)`
- Produces: `AgentMemory.retrieve_context(turn: ConversationTurn) -> dict[str, Any]`
- Produces: `AgentMemory.update(turn: ConversationTurn) -> dict[str, Any]`
- Produces: `AgentMemory.to_dict() -> dict[str, Any]`

- [ ] **Step 1: Write failing domain tests**

Create `tests/test_memory_domain.py`:

```python
from companion_bot.memory import AgentMemory, ConversationTurn


def test_retrieve_context_is_empty_before_first_turn():
    memory = AgentMemory()

    context = memory.retrieve_context(
        ConversationTurn(
            user_id="telegram:123",
            channel="telegram",
            message_text="你好",
            message_timestamp="2026-06-22T06:46:00+00:00",
        )
    )

    assert context == {
        "speaker_state": None,
        "recent_current_events": [],
        "compressed_events": [],
        "known_characters": [],
    }


def test_update_records_user_and_karen_turn():
    memory = AgentMemory()

    update = memory.update(
        ConversationTurn(
            user_id="telegram:123",
            channel="telegram",
            message_text="有点饿了",
            message_timestamp="2026-06-22T09:22:00+00:00",
            assistant_reply="要不要先吃点简单的？",
        )
    )

    assert update["feedback_mode"] == "conversation_observation"
    assert update["updated_person"]["name"] == "user"
    assert update["updated_person"]["recent_events"] == [
        "2026-06-22T09:22:00+00:00 via telegram: user said: 有点饿了 | Karen replied: 要不要先吃点简单的？"
    ]
    assert update["added_current_event"] == {
        "time": "2026-06-22T09:22:00+00:00",
        "location": "telegram",
        "characters": ["user", "Karen"],
        "action": 'user said "有点饿了". Karen replied "要不要先吃点简单的？".',
        "known_scope": "observable_so_far",
    }


def test_retrieve_context_after_update_returns_compact_state():
    memory = AgentMemory()
    memory.update(
        ConversationTurn(
            user_id="telegram:123",
            channel="telegram",
            message_text="今天有点累",
            message_timestamp="2026-06-22T10:00:00+00:00",
            assistant_reply="那我们慢一点。",
        )
    )

    context = memory.retrieve_context(
        ConversationTurn(
            user_id="telegram:123",
            channel="telegram",
            message_text="还想聊一会儿",
            message_timestamp="2026-06-22T10:05:00+00:00",
        )
    )

    assert context["speaker_state"]["name"] == "user"
    assert context["known_characters"] == ["user"]
    assert context["recent_current_events"][-1]["action"] == (
        'user said "今天有点累". Karen replied "那我们慢一点。".'
    )


def test_current_events_are_compressed_after_limit():
    memory = AgentMemory(max_current_events=2)

    for index in range(4):
        memory.update(
            ConversationTurn(
                user_id="telegram:123",
                channel="telegram",
                message_text=f"message {index}",
                message_timestamp=f"2026-06-22T10:0{index}:00+00:00",
                assistant_reply=f"reply {index}",
            )
        )

    data = memory.to_dict()
    assert len(data["current_events"]) == 2
    assert len(data["compressed_events"]) == 2
    assert data["compressed_events"][-1]["known_scope"] == "compressed_from_observed_history"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
/home/xuyao/karen/.worktrees/deepseek-llm-connectivity/.venv/bin/python -m pytest tests/test_memory_domain.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'companion_bot.memory'`.

- [ ] **Step 3: Implement domain module**

Create `companion_bot/memory.py` with dataclasses adapted from `~/friends/ac/memory.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConversationTurn:
    user_id: str
    channel: str
    message_text: str
    message_timestamp: str | None = None
    assistant_reply: str | None = None


@dataclass
class PersonState:
    name: str
    goals: list[str] = field(default_factory=list)
    needs: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    recent_events: list[str] = field(default_factory=list)
    behavior_patterns: list[str] = field(default_factory=list)
    interpretation_patterns: list[str] = field(default_factory=list)
    traits_or_notes: list[str] = field(default_factory=list)
    relationships: dict[str, str] = field(default_factory=dict)

    def compact(self, max_items: int = 5) -> dict[str, Any]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, list):
                data[key] = value[-max_items:]
        return data


@dataclass
class EventMemory:
    time: str
    location: str
    characters: list[str]
    action: str
    known_scope: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentMemory:
    people: dict[str, PersonState] = field(default_factory=dict)
    current_events: list[EventMemory] = field(default_factory=list)
    compressed_events: list[EventMemory] = field(default_factory=list)
    max_current_events: int = 8
    max_recent_events_per_person: int = 8

    def retrieve_context(self, turn: ConversationTurn) -> dict[str, Any]:
        speaker_state = self.people.get("user")
        return {
            "speaker_state": speaker_state.compact() if speaker_state else None,
            "recent_current_events": [
                event.to_dict() for event in self.current_events[-5:]
            ],
            "compressed_events": [
                event.to_dict() for event in self.compressed_events[-5:]
            ],
            "known_characters": sorted(self.people.keys()),
        }

    def update(self, turn: ConversationTurn) -> dict[str, Any]:
        person = self.people.setdefault("user", PersonState(name="user"))
        event = EventMemory(
            time=_format_time(turn),
            location=turn.channel or "unknown channel",
            characters=_characters_for(turn),
            action=_event_action(turn),
            known_scope="observable_so_far",
        )
        self.current_events.append(event)
        compressed_now = self._compress_if_needed()
        self._update_person_state(person, turn)
        return {
            "updated_person": person.compact(),
            "added_current_event": event.to_dict(),
            "compressed_events_added": [
                event.to_dict() for event in compressed_now
            ],
            "feedback_mode": "conversation_observation",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "people": {
                name: state.compact(max_items=99)
                for name, state in self.people.items()
            },
            "current_events": [event.to_dict() for event in self.current_events],
            "compressed_events": [
                event.to_dict() for event in self.compressed_events
            ],
        }

    def _compress_if_needed(self) -> list[EventMemory]:
        if len(self.current_events) <= self.max_current_events:
            return []

        overflow = self.current_events[: -self.max_current_events]
        self.current_events = self.current_events[-self.max_current_events :]
        speakers = sorted({name for event in overflow for name in event.characters})
        summary = "; ".join(event.action for event in overflow)
        compressed = EventMemory(
            time=f"{overflow[0].time}..{overflow[-1].time}",
            location=overflow[-1].location,
            characters=speakers,
            action=f"Compressed prior events: {summary}",
            known_scope="compressed_from_observed_history",
        )
        self.compressed_events.append(compressed)
        return [compressed]

    def _update_person_state(self, person: PersonState, turn: ConversationTurn) -> None:
        person.recent_events.append(_recent_event_note(turn))
        person.recent_events = person.recent_events[
            -self.max_recent_events_per_person :
        ]


def _format_time(turn: ConversationTurn) -> str:
    return turn.message_timestamp or "current"


def _characters_for(turn: ConversationTurn) -> list[str]:
    if turn.assistant_reply:
        return ["user", "Karen"]
    return ["user"]


def _event_action(turn: ConversationTurn) -> str:
    action = f'user said "{turn.message_text}".'
    if turn.assistant_reply:
        action += f' Karen replied "{turn.assistant_reply}".'
    return action


def _recent_event_note(turn: ConversationTurn) -> str:
    note = f"{_format_time(turn)} via {turn.channel}: user said: {turn.message_text}"
    if turn.assistant_reply:
        note += f" | Karen replied: {turn.assistant_reply}"
    return note
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
/home/xuyao/karen/.worktrees/deepseek-llm-connectivity/.venv/bin/python -m pytest tests/test_memory_domain.py -v
```

Expected: all tests in `tests/test_memory_domain.py` pass.

- [ ] **Step 5: Commit**

```bash
git add companion_bot/memory.py tests/test_memory_domain.py
git commit -m "feat: add conversation memory domain"
```

---

### Task 2: Memory Service REST APIs

**Files:**
- Modify: `companion_bot/services/memory.py`
- Modify: `tests/test_memory_service.py`

**Interfaces:**
- Consumes: `AgentMemory`, `ConversationTurn`
- Produces: `POST /v1/users/{user_id}/memory/context`
- Produces: `POST /v1/users/{user_id}/memory/turns`
- Preserves: `GET /v1/users/{user_id}/memories`, `POST /v1/users/{user_id}/memories`

- [ ] **Step 1: Write failing service tests**

Append to `tests/test_memory_service.py`:

```python
def test_memory_context_endpoint_returns_online_context():
    with TestClient(app) as client:
        response = client.post(
            "/v1/users/telegram:123/memory/context",
            json={
                "channel": "telegram",
                "message_text": "你好",
                "message_timestamp": "2026-06-22T06:46:00+00:00",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "telegram:123",
        "context": {
            "speaker_state": None,
            "recent_current_events": [],
            "compressed_events": [],
            "known_characters": [],
        },
    }


def test_memory_turn_endpoint_updates_online_memory():
    with TestClient(app) as client:
        update_response = client.post(
            "/v1/users/telegram:123/memory/turns",
            json={
                "channel": "telegram",
                "message_text": "有点饿了",
                "message_timestamp": "2026-06-22T09:22:00+00:00",
                "assistant_reply": "要不要先吃点简单的？",
            },
        )
        context_response = client.post(
            "/v1/users/telegram:123/memory/context",
            json={
                "channel": "telegram",
                "message_text": "还想吃甜的",
                "message_timestamp": "2026-06-22T09:25:00+00:00",
            },
        )

    assert update_response.status_code == 200
    assert update_response.json()["updated"] is True
    assert context_response.status_code == 200
    assert context_response.json()["context"]["speaker_state"]["recent_events"] == [
        "2026-06-22T09:22:00+00:00 via telegram: user said: 有点饿了 | Karen replied: 要不要先吃点简单的？"
    ]
```

Update `test_startup_clears_existing_memory_store` to also seed `_agent_memories` after it exists:

```python
from companion_bot.memory import AgentMemory, ConversationTurn
from companion_bot.services.memory import _agent_memories, _memory_store, app
```

and inside the test:

```python
    online_memory = AgentMemory()
    online_memory.update(
        ConversationTurn(
            user_id="telegram:stale",
            channel="telegram",
            message_text="stale",
            assistant_reply="stale reply",
        )
    )
    _agent_memories["telegram:stale"] = online_memory
```

Then after the existing GET assertion, add:

```python
        context_response = client.post(
            "/v1/users/telegram:stale/memory/context",
            json={"channel": "telegram", "message_text": "fresh"},
        )

    assert context_response.json()["context"]["speaker_state"] is None
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
/home/xuyao/karen/.worktrees/deepseek-llm-connectivity/.venv/bin/python -m pytest tests/test_memory_service.py -v
```

Expected: fail with missing `_agent_memories` import or 404 for new endpoints.

- [ ] **Step 3: Implement REST models and endpoints**

Modify `companion_bot/services/memory.py`:

```python
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

from companion_bot.memory import AgentMemory, ConversationTurn
```

Add models:

```python
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
```

Add store and clear it in lifespan:

```python
_agent_memories: dict[str, AgentMemory] = defaultdict(AgentMemory)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _memory_store.clear()
    _agent_memories.clear()
    yield
```

Add helper:

```python
def _conversation_turn(user_id: str, request: MemoryContextRequest | ConversationTurnRequest) -> ConversationTurn:
    return ConversationTurn(
        user_id=user_id,
        channel=request.channel,
        message_text=request.message_text,
        message_timestamp=request.message_timestamp,
        assistant_reply=getattr(request, "assistant_reply", None),
    )
```

Add endpoints:

```python
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
```

- [ ] **Step 4: Run service tests**

Run:

```bash
/home/xuyao/karen/.worktrees/deepseek-llm-connectivity/.venv/bin/python -m pytest tests/test_memory_service.py -v
```

Expected: all memory service tests pass.

- [ ] **Step 5: Commit**

```bash
git add companion_bot/services/memory.py tests/test_memory_service.py
git commit -m "feat: expose conversation memory api"
```

---

### Task 3: Chat Service Memory Integration

**Files:**
- Modify: `companion_bot/services/chat.py`
- Modify: `tests/test_chat_service.py`

**Interfaces:**
- Consumes: `POST /v1/users/{user_id}/memory/context`
- Consumes: `POST /v1/users/{user_id}/memory/turns`
- Produces: LLM messages containing optional memory system context before latest user message.

- [ ] **Step 1: Update chat service tests**

In `tests/test_chat_service.py`, add helper payloads:

```python
EMPTY_CONTEXT_PAYLOAD = {
    "user_id": "telegram:123",
    "context": {
        "speaker_state": None,
        "recent_current_events": [],
        "compressed_events": [],
        "known_characters": [],
    },
}

NON_EMPTY_CONTEXT_PAYLOAD = {
    "user_id": "telegram:123",
    "context": {
        "speaker_state": {
            "name": "user",
            "goals": [],
            "needs": [],
            "concerns": [],
            "recent_events": ["2026-06-22T09:22:00+00:00 via telegram: user said: 有点饿了 | Karen replied: 要不要先吃点简单的？"],
            "behavior_patterns": [],
            "interpretation_patterns": [],
            "traits_or_notes": [],
            "relationships": {},
        },
        "recent_current_events": [],
        "compressed_events": [],
        "known_characters": ["user"],
    },
}
```

Update the existing LLM success test to mock context and turn endpoints:

```python
    respx.post("http://memory.test/v1/users/telegram:123/memory/context").mock(
        return_value=httpx.Response(200, json=NON_EMPTY_CONTEXT_PAYLOAD)
    )
    turn_route = respx.post("http://memory.test/v1/users/telegram:123/memory/turns").mock(
        return_value=httpx.Response(200, json={"updated": True, "memory_update": {}})
    )
```

Assert the DeepSeek request contains three messages:

```python
    llm_body = json.loads(llm_route.calls[0].request.content)
    assert [message["role"] for message in llm_body["messages"]] == [
        "system",
        "system",
        "user",
    ]
    assert "Known memory context before the latest user message:" in llm_body["messages"][1]["content"]
    assert "有点饿了" in llm_body["messages"][1]["content"]
    assert json.loads(turn_route.calls[0].request.content) == {
        "channel": "telegram",
        "message_text": "有点饿了",
        "message_timestamp": "2026-06-22T09:22:00+00:00",
        "assistant_reply": "要不要先吃点简单的？",
    }
```

Add a test for empty context:

```python
@respx.mock
def test_chat_reply_omits_memory_message_when_context_is_empty(monkeypatch):
    monkeypatch.setenv("MEMORY_SERVICE_URL", "http://memory.test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    respx.post("http://memory.test/v1/users/telegram:123/memory/context").mock(
        return_value=httpx.Response(200, json=EMPTY_CONTEXT_PAYLOAD)
    )
    respx.post("http://memory.test/v1/users/telegram:123/memory/turns").mock(
        return_value=httpx.Response(200, json={"updated": True, "memory_update": {}})
    )
    llm_route = respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "我在。"}}]},
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
    llm_body = json.loads(llm_route.calls[0].request.content)
    assert [message["role"] for message in llm_body["messages"]] == ["system", "user"]
```

Update memory-failure test to mock new endpoints as 503 and assert reply still succeeds.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
/home/xuyao/karen/.worktrees/deepseek-llm-connectivity/.venv/bin/python -m pytest tests/test_chat_service.py -v
```

Expected: fail because chat-service still calls old `/memories` endpoints.

- [ ] **Step 3: Implement context models and helpers**

Modify `companion_bot/services/chat.py`:

```python
import json
from typing import Any
```

Replace old memory response models with:

```python
class MemoryContextResponse(BaseModel):
    user_id: str
    context: dict[str, Any]


class ConversationTurnResponse(BaseModel):
    updated: bool
    memory_update: dict[str, Any]
```

Add:

```python
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
```

- [ ] **Step 4: Wire helpers into reply path**

Change `build_reply` signature:

```python
async def build_reply(request: ChatReplyRequest, memory_context: dict[str, Any]) -> str:
```

Inside it, build messages:

```python
        messages = [ChatMessage(role="system", content=SYSTEM_PROMPT)]
        memory_message = format_memory_context_message(memory_context)
        if memory_message is not None:
            messages.append(memory_message)
        messages.append(ChatMessage(role="user", content=request.message_text))
        return await generate_chat_reply(messages=messages, settings=settings)
```

Change endpoint:

```python
@app.post("/v1/chat/reply", response_model=ChatReplyResponse)
async def reply(request: ChatReplyRequest) -> ChatReplyResponse:
    settings = load_chat_settings()
    memory_context = await fetch_memory_context(request, settings.memory_service_url)
    reply_text = await build_reply(request, memory_context)
    await store_conversation_turn(request, reply_text, settings.memory_service_url)
    return ChatReplyResponse(reply_text=reply_text)
```

Remove old `fetch_memories`, `store_interaction_note`, `MemoryRecord`, and `MemoriesResponse` from `chat.py`.

- [ ] **Step 5: Run chat tests**

Run:

```bash
/home/xuyao/karen/.worktrees/deepseek-llm-connectivity/.venv/bin/python -m pytest tests/test_chat_service.py -v
```

Expected: all chat service tests pass.

- [ ] **Step 6: Commit**

```bash
git add companion_bot/services/chat.py tests/test_chat_service.py
git commit -m "feat: connect chat service to conversation memory"
```

---

### Task 4: Docs and Full Verification

**Files:**
- Modify: `README.md`

**Interfaces:**
- Documents service startup, new memory endpoints, and in-memory limitation.

- [ ] **Step 1: Update README**

In `README.md`, replace the memory API section with:

````markdown
Read legacy flat memories:

```bash
curl http://127.0.0.1:8001/v1/users/telegram:123/memories
```

Store legacy flat memory:

```bash
curl -X POST http://127.0.0.1:8001/v1/users/telegram:123/memories \
  -H 'Content-Type: application/json' \
  -d '{"kind":"interaction_note","content":"User sent a message through a chat channel.","source":"chat-service"}'
```

Read conversation memory context:

```bash
curl -X POST http://127.0.0.1:8001/v1/users/telegram:123/memory/context \
  -H 'Content-Type: application/json' \
  -d '{"channel":"telegram","message_text":"你好","message_timestamp":"2026-06-22T06:46:00+00:00"}'
```

Store a completed conversation turn:

```bash
curl -X POST http://127.0.0.1:8001/v1/users/telegram:123/memory/turns \
  -H 'Content-Type: application/json' \
  -d '{"channel":"telegram","message_text":"有点饿了","message_timestamp":"2026-06-22T09:22:00+00:00","assistant_reply":"要不要先吃点简单的？"}'
```
````

Add:

```markdown
Memory is currently process-local and resets when `memory-service` restarts.
```

- [ ] **Step 2: Run full test suite**

Run:

```bash
/home/xuyao/karen/.worktrees/deepseek-llm-connectivity/.venv/bin/python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Check working tree**

Run:

```bash
git status --short
```

Expected: only `README.md` modified.

- [ ] **Step 4: Commit docs**

```bash
git add README.md
git commit -m "docs: document conversation memory api"
```

---

## Final Review

After all tasks complete:

- Run full tests again:

```bash
/home/xuyao/karen/.worktrees/deepseek-llm-connectivity/.venv/bin/python -m pytest -v
```

- Inspect commits:

```bash
git log --oneline --decorate -6
```

- Inspect status:

```bash
git status --short --branch
```

- Request code review using `superpowers:requesting-code-review`.
- Fix any review findings with separate commits.
- Push branch:

```bash
git push -u origin feature/ac-memory-migration
```
