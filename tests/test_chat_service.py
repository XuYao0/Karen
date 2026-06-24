import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from companion_bot.services.chat import app


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
def test_chat_reply_uses_deepseek_latest_message_only(monkeypatch):
    monkeypatch.setenv("MEMORY_SERVICE_URL", "http://memory.test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    respx.post("http://memory.test/v1/users/telegram:123/memory/context").mock(
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
    respx.post("http://memory.test/v1/users/telegram:123/memory/turns").mock(
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
    assert response.json() == {
        "reply_text": "我在认真想怎么回应你，但刚刚有点卡住了。你可以再发我一次，我会继续陪你。"
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
