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

Required environment variables:

- `TELEGRAM_BOT_TOKEN` only for `telegram-gateway`

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
  -d '{"kind":"interaction_note","content":"User sent a message through a chat channel.","source":"chat-service"}'
```
