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
