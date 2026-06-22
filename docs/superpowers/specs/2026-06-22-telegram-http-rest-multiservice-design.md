# Telegram HTTP REST Multiservice Design

## Context

This project is an emotionally supportive AI companion with memory. The first interaction module will run through a Telegram bot, similar in deployment style to an always-available chat companion.

The first implementation should establish a multiservice architecture rather than a single monolith. It should prioritize clear service boundaries, local operability, and future replacement of placeholder logic with a real LLM and durable memory.

## Goals

- Run a Telegram bot through long polling.
- Keep Telegram-specific code isolated in an edge gateway service.
- Route user messages through a chat service over HTTP REST.
- Keep memory access behind a separate memory service API.
- Provide a warm placeholder response while leaving the chat implementation replaceable.
- Make local development possible with simple Python commands.

## Non-Goals

- No production webhook deployment in this version.
- No durable database storage in this version.
- No real LLM integration in this version.
- No full memory extraction or summarization pipeline in this version.
- No authentication between local services in this version.

## Architecture

The first version will contain three Python services.

### `telegram-gateway`

`telegram-gateway` owns Telegram integration.

Responsibilities:

- Start a Telegram bot with long polling.
- Read `TELEGRAM_BOT_TOKEN` and `CHAT_SERVICE_URL` from environment variables.
- Handle `/start`.
- Handle normal text messages.
- Send user messages to `chat-service`.
- Send the returned reply text back to Telegram.
- Reply with a warm fallback message when `chat-service` is unavailable.
- Ignore or gently decline unsupported non-text messages.

It must not generate companion replies directly and must not call `memory-service`.

### `chat-service`

`chat-service` owns conversation orchestration.

Responsibilities:

- Expose `POST /v1/chat/reply`.
- Read `MEMORY_SERVICE_URL` from environment variables.
- Request memories for the user from `memory-service`.
- Generate a local placeholder emotionally supportive reply.
- Best-effort record a simple memory or interaction note through `memory-service`.
- Continue replying if `memory-service` is unavailable.

The placeholder response is intentionally simple. The important boundary is that Telegram integration calls this service rather than embedding chat behavior.

### `memory-service`

`memory-service` owns memory APIs.

Responsibilities:

- Expose `GET /v1/users/{user_id}/memories`.
- Expose `POST /v1/users/{user_id}/memories`.
- Store memories in process memory for the first version.
- Return an empty list for users with no memories.

The in-memory store is a temporary implementation behind a stable API. Data loss on restart is expected in this version.

## API Contracts

### `POST /v1/chat/reply`

Request:

```json
{
  "user_id": "telegram:123456",
  "channel": "telegram",
  "message_text": "I had a hard day."
}
```

Response:

```json
{
  "reply_text": "I'm here with you. It sounds like today took a lot out of you."
}
```

Failure behavior:

- Invalid requests return `422`.
- Unexpected service errors return `500`.
- Memory-service failures do not fail the chat response.

### `GET /v1/users/{user_id}/memories`

Response:

```json
{
  "user_id": "telegram:123456",
  "memories": []
}
```

### `POST /v1/users/{user_id}/memories`

Request:

```json
{
  "kind": "interaction_note",
  "content": "User sent a message through a chat channel.",
  "source": "chat-service"
}
```

Response:

```json
{
  "stored": true
}
```

## Local Runtime

The services run as separate local processes.

```bash
python -m companion_bot.services.memory
python -m companion_bot.services.chat
python -m companion_bot.telegram_gateway
```

Default local URLs:

- `memory-service`: `http://127.0.0.1:8001`
- `chat-service`: `http://127.0.0.1:8002`

Environment variables:

- `TELEGRAM_BOT_TOKEN`: required by `telegram-gateway`.
- `CHAT_SERVICE_URL`: optional for `telegram-gateway`, defaults to `http://127.0.0.1:8002`.
- `MEMORY_SERVICE_URL`: optional for `chat-service`, defaults to `http://127.0.0.1:8001`.

## Error Handling

- `telegram-gateway` catches chat-service errors and sends a short supportive fallback reply.
- `chat-service` catches memory-service errors, logs them, and continues with a memory-free reply.
- `memory-service` validates request shape and returns normal FastAPI validation errors for invalid input.
- Each process logs startup configuration without printing secrets.

## Testing Strategy

Unit tests:

- Configuration defaults and missing required Telegram token behavior.
- Memory-service stores and returns in-memory records.
- Chat-service returns a reply even when memory-service is unavailable.
- Chat-service attempts to read and write memory through the configured memory URL.

Integration-style tests:

- Telegram gateway handler forwards text messages to chat-service and sends the returned reply.
- Telegram gateway handler returns fallback text when chat-service fails.

External network tests against the real Telegram API are out of scope for the first version.

## Implementation Notes

- Use Python.
- Use FastAPI for `chat-service` and `memory-service`.
- Use `python-telegram-bot` for `telegram-gateway`.
- Use `httpx` for service-to-service HTTP calls.
- Keep service modules small and independently testable.
- Use typed request and response models for REST boundaries.
