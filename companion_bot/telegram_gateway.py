import logging
from datetime import timezone
from typing import Any

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

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


def serialize_message_timestamp(update: Update) -> str | None:
    if update.message is None or update.message.date is None:
        return None
    return update.message.date.astimezone(timezone.utc).isoformat()


async def fetch_chat_reply(
    user_id: str,
    message_text: str,
    chat_service_url: str,
    message_timestamp: str | None = None,
) -> str:
    payload: dict[str, str] = {
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
        payload = response.json()
        return str(payload["reply_text"])


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
        reply_text = await fetch_chat_reply(
            user_id,
            message_text,
            chat_service_url,
            message_timestamp=serialize_message_timestamp(update),
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        logger.warning("Failed to fetch chat reply for user_id=%s", user_id)
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
    application.add_handler(MessageHandler(filters.COMMAND, handle_unsupported_message))
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
    logger.info(
        "Starting telegram-gateway with chat_service_url=%s", settings.chat_service_url
    )
    application.run_polling()


if __name__ == "__main__":
    main()
