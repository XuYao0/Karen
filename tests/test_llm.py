import json

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
    assert json.loads(request.content) == {
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
    assert "thinking" not in json.loads(route.calls.last.request.content)


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
