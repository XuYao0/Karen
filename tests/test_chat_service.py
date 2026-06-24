import json
from urllib.parse import urlparse

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from companion_bot.services.chat import LLM_FALLBACK_REPLY, app
from companion_bot.services.memory import (
    _agent_memories,
    _memory_store,
    app as memory_app,
)


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
            "recent_events": [
                "2026-06-22T09:22:00+00:00 via telegram: user said: 有点饿了 | Karen replied: 要不要先吃点简单的？"
            ],
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


@pytest.fixture(autouse=True)
def clear_llm_env(monkeypatch):
    for key in (
        "DEEPSEEK_API_KEY",
        "LLM_PROVIDER",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "LLM_REASONING_EFFORT",
        "LLM_THINKING_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)


@respx.mock
def test_chat_reply_includes_memory_context_and_persists_turn(monkeypatch):
    monkeypatch.setenv("MEMORY_SERVICE_URL", "http://memory.test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    context_route = respx.post(
        "http://memory.test/v1/users/telegram:123/memory/context"
    ).mock(
        return_value=httpx.Response(200, json=NON_EMPTY_CONTEXT_PAYLOAD)
    )
    turn_route = respx.post(
        "http://memory.test/v1/users/telegram:123/memory/turns"
    ).mock(
        return_value=httpx.Response(200, json={"updated": True, "memory_update": {}})
    )
    llm_route = respx.post("https://api.deepseek.com/chat/completions").mock(
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
    assert context_route.called
    assert json.loads(context_route.calls[0].request.content) == {
        "channel": "telegram",
        "message_text": "你好",
        "message_timestamp": "2026-06-22T06:46:00+00:00",
    }
    assert turn_route.called
    assert json.loads(turn_route.calls[0].request.content) == {
        "channel": "telegram",
        "message_text": "你好",
        "message_timestamp": "2026-06-22T06:46:00+00:00",
        "assistant_reply": "你好，我听见你了。",
    }
    llm_body = json.loads(llm_route.calls[0].request.content)
    assert [message["role"] for message in llm_body["messages"]] == [
        "system",
        "system",
        "user",
    ]
    assert "Known memory context before the latest user message:" in llm_body["messages"][1]["content"]
    assert "有点饿了" in llm_body["messages"][1]["content"]


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


@respx.mock
def test_chat_reply_logs_provider_model_and_error_type_on_llm_failure(
    monkeypatch, caplog
):
    monkeypatch.setenv("MEMORY_SERVICE_URL", "http://memory.test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    respx.post("http://memory.test/v1/users/telegram:123/memory/context").mock(
        return_value=httpx.Response(200, json=EMPTY_CONTEXT_PAYLOAD)
    )
    turn_route = respx.post(
        "http://memory.test/v1/users/telegram:123/memory/turns"
    ).mock(
        return_value=httpx.Response(200, json={"updated": True, "memory_update": {}})
    )
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"})
    )

    caplog.clear()
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
    assert response.json() == {"reply_text": LLM_FALLBACK_REPLY}
    assert turn_route.called
    assert json.loads(turn_route.calls[0].request.content) == {
        "channel": "telegram",
        "message_text": "你好",
        "message_timestamp": "2026-06-22T06:46:00+00:00",
        "assistant_reply": LLM_FALLBACK_REPLY,
    }
    log_text = caplog.text
    assert "Failed to generate LLM reply" in log_text
    assert "provider=deepseek" in log_text
    assert "model=deepseek-v4-pro" in log_text
    assert "user_id=telegram:123" in log_text
    assert "channel=telegram" in log_text
    assert "error_type=LLMClientError" in log_text
    assert "deepseek-key" not in log_text


@respx.mock
def test_chat_reply_logs_unknown_provider_and_model_on_settings_failure(
    monkeypatch, caplog
):
    monkeypatch.setenv("MEMORY_SERVICE_URL", "http://memory.test")
    respx.post("http://memory.test/v1/users/telegram:123/memory/context").mock(
        return_value=httpx.Response(200, json=EMPTY_CONTEXT_PAYLOAD)
    )
    respx.post("http://memory.test/v1/users/telegram:123/memory/turns").mock(
        return_value=httpx.Response(200, json={"updated": True, "memory_update": {}})
    )

    caplog.clear()
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
    log_text = caplog.text
    assert "Failed to generate LLM reply" in log_text
    assert "provider=unknown" in log_text
    assert "model=unknown" in log_text
    assert "user_id=telegram:123" in log_text
    assert "channel=telegram" in log_text
    assert "error_type=RuntimeError" in log_text


@respx.mock
def test_chat_reply_continues_when_memory_service_fails(monkeypatch):
    monkeypatch.setenv("MEMORY_SERVICE_URL", "http://memory.test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    respx.post("http://memory.test/v1/users/telegram:123/memory/context").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"})
    )
    respx.post("http://memory.test/v1/users/telegram:123/memory/turns").mock(
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


def test_chat_reply_uses_real_memory_service_contract(monkeypatch):
    monkeypatch.setenv("MEMORY_SERVICE_URL", "http://memory.test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    _memory_store.clear()
    _agent_memories.clear()
    llm_bodies = []
    original_async_client = httpx.AsyncClient

    class RoutedAsyncClient:
        def __init__(self, *args, **kwargs):
            self._kwargs = kwargs
            self._clients = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            for client in self._clients:
                await client.aclose()

        async def post(self, url, *args, **kwargs):
            parsed = urlparse(str(url))
            if parsed.netloc == "memory.test":
                client = original_async_client(
                    transport=httpx.ASGITransport(app=memory_app),
                    base_url="http://memory.test",
                    timeout=self._kwargs.get("timeout"),
                )
                self._clients.append(client)
                path = parsed.path
                if parsed.query:
                    path = f"{path}?{parsed.query}"
                return await client.post(path, *args, **kwargs)

            if parsed.netloc == "api.deepseek.com":
                llm_bodies.append(kwargs["json"])
                reply = f"reply {len(llm_bodies)}"
                return httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": reply}}]},
                    request=httpx.Request("POST", str(url)),
                )

            raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(httpx, "AsyncClient", RoutedAsyncClient)

    with TestClient(app) as client:
        first_response = client.post(
            "/v1/chat/reply",
            json={
                "user_id": "telegram:123",
                "channel": "telegram",
                "message_text": "有点饿了",
                "message_timestamp": "2026-06-22T09:22:00+00:00",
            },
        )
        second_response = client.post(
            "/v1/chat/reply",
            json={
                "user_id": "telegram:123",
                "channel": "telegram",
                "message_text": "还想吃甜的",
                "message_timestamp": "2026-06-22T09:25:00+00:00",
            },
        )

    assert first_response.status_code == 200
    assert first_response.json() == {"reply_text": "reply 1"}
    assert second_response.status_code == 200
    assert second_response.json() == {"reply_text": "reply 2"}
    assert [message["role"] for message in llm_bodies[0]["messages"]] == [
        "system",
        "user",
    ]
    assert [message["role"] for message in llm_bodies[1]["messages"]] == [
        "system",
        "system",
        "user",
    ]
    assert "有点饿了" in llm_bodies[1]["messages"][1]["content"]
    assert "reply 1" in llm_bodies[1]["messages"][1]["content"]
