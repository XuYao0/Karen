import json

import httpx
import respx
from fastapi.testclient import TestClient

from companion_bot.services.chat import app


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
    post_route = respx.post("http://memory.test/v1/users/telegram:123/memories").mock(
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
    assert post_route.called
    assert json.loads(post_route.calls[0].request.content) == {
        "kind": "interaction_note",
        "content": "User sent a message through a chat channel.",
        "source": "chat-service",
    }
    request_body = json.loads(deepseek_route.calls.last.request.content)
    assert request_body["messages"] == [
        {
            "role": "system",
            "content": "You are Karen, a warm and emotionally present AI friend. Reply naturally and briefly.",
        },
        {"role": "user", "content": "你好"},
    ]
    assert "This must not be sent to the LLM yet." not in str(request_body)


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
