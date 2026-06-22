from dataclasses import dataclass, field
from datetime import datetime, timezone
import json

import httpx
import pytest
import respx
from telegram.ext import MessageHandler, filters

from companion_bot.telegram_gateway import (
    build_application,
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
    date: datetime | None = None
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
    route = respx.post("http://chat.test/v1/chat/reply").mock(
        return_value=httpx.Response(200, json={"reply_text": "warm reply"})
    )

    reply = await fetch_chat_reply(
        user_id="telegram:123",
        message_text="hello",
        chat_service_url="http://chat.test",
    )

    assert reply == "warm reply"
    assert json.loads(route.calls.last.request.content) == {
        "user_id": "telegram:123",
        "channel": "telegram",
        "message_text": "hello",
    }


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

    assert json.loads(route.calls.last.request.content)["message_timestamp"] == (
        "2026-06-22T06:46:00+00:00"
    )


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


def test_build_application_routes_unknown_commands_to_unsupported_message():
    application = build_application(token="test-token")

    command_handlers = application.handlers[0]
    assert any(
        isinstance(handler, MessageHandler)
        and handler.callback is handle_unsupported_message
        and handler.filters == filters.COMMAND
        for handler in command_handlers
    )
