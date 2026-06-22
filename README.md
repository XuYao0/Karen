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
DEEPSEEK_API_KEY=your-key python -m companion_bot.services.chat
```

```bash
TELEGRAM_BOT_TOKEN=your-token python -m companion_bot.telegram_gateway
```

Default local service URLs:

- memory-service: `http://127.0.0.1:8001`
- chat-service: `http://127.0.0.1:8002`

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

## HTTP APIs

Chat reply:

```bash
curl -X POST http://127.0.0.1:8002/v1/chat/reply \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"telegram:123","channel":"telegram","message_text":"I had a hard day.","message_timestamp":"2026-06-22T06:46:00+00:00"}'
```

Read memories:

```bash
curl http://127.0.0.1:8001/v1/users/telegram:123/memories
```

Store memory:

```bash
curl -X POST http://127.0.0.1:8001/v1/users/telegram:123/memories \
  -H 'Content-Type: application/json' \
  -d '{"kind":"interaction_note","content":"User sent a message through a chat channel.","source":"chat-service"}'
```

## LLM Smoke Test

With `memory-service` and `chat-service` running:

```bash
curl -X POST http://127.0.0.1:8002/v1/chat/reply \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"telegram:123","channel":"telegram","message_text":"你好","message_timestamp":"2026-06-22T06:46:00+00:00"}'
```

If `DEEPSEEK_API_KEY` is configured for `chat-service`, the response should come from DeepSeek. If DeepSeek is unavailable, `chat-service` returns a warm fallback.
