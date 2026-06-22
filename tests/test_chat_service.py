import json

import httpx
import respx
from fastapi.testclient import TestClient

from companion_bot.services.chat import app


@respx.mock
def test_chat_reply_reads_and_writes_memory(monkeypatch):
    monkeypatch.setenv("MEMORY_SERVICE_URL", "http://memory.test")
    respx.get("http://memory.test/v1/users/telegram:123/memories").mock(
        return_value=httpx.Response(
            200,
            json={
                "user_id": "telegram:123",
                "memories": [
                    {
                        "kind": "preference",
                        "content": "User likes gentle check-ins.",
                        "source": "test",
                    }
                ],
            },
        )
    )
    post_route = respx.post("http://memory.test/v1/users/telegram:123/memories").mock(
        return_value=httpx.Response(200, json={"stored": True})
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/reply",
            json={
                "user_id": "telegram:123",
                "channel": "telegram",
                "message_text": "I had a hard day.",
            },
    )

    assert response.status_code == 200
    assert "I'm here with you" in response.json()["reply_text"]
    assert post_route.called
    assert json.loads(post_route.calls[0].request.content) == {
        "kind": "interaction_note",
        "content": "User sent a message through a chat channel.",
        "source": "chat-service",
    }


@respx.mock
def test_chat_reply_continues_when_memory_service_fails(monkeypatch):
    monkeypatch.setenv("MEMORY_SERVICE_URL", "http://memory.test")
    respx.get("http://memory.test/v1/users/telegram:123/memories").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"})
    )
    respx.post("http://memory.test/v1/users/telegram:123/memories").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"})
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
    assert response.json() == {
        "reply_text": "I'm here with you. It sounds like this moment feels heavy, and you do not have to hold it alone."
    }
