from fastapi.testclient import TestClient

from companion_bot.memory import AgentMemory, ConversationTurn
from companion_bot.services.memory import _agent_memories, _memory_store, app


def test_get_memories_returns_empty_list_for_new_user():
    with TestClient(app) as client:
        response = client.get("/v1/users/telegram:123/memories")

    assert response.status_code == 200
    assert response.json() == {"user_id": "telegram:123", "memories": []}


def test_post_memory_stores_record_for_user():
    with TestClient(app) as client:
        create_response = client.post(
            "/v1/users/telegram:123/memories",
            json={
                "kind": "interaction_note",
                "content": "User sent a message through Telegram.",
                "source": "chat-service",
            },
        )
        get_response = client.get("/v1/users/telegram:123/memories")

    assert create_response.status_code == 200
    assert create_response.json() == {"stored": True}
    assert get_response.status_code == 200
    assert get_response.json() == {
        "user_id": "telegram:123",
        "memories": [
            {
                "kind": "interaction_note",
                "content": "User sent a message through Telegram.",
                "source": "chat-service",
            }
        ],
    }


def test_startup_clears_existing_memory_store():
    _memory_store["telegram:stale"].append(
        {
            "kind": "interaction_note",
            "content": "stale",
            "source": "test",
        }
    )
    online_memory = AgentMemory()
    online_memory.update(
        ConversationTurn(
            user_id="telegram:stale",
            channel="telegram",
            message_text="stale",
            assistant_reply="stale reply",
        )
    )
    _agent_memories["telegram:stale"] = online_memory

    with TestClient(app) as client:
        response = client.get("/v1/users/telegram:stale/memories")
        context_response = client.post(
            "/v1/users/telegram:stale/memory/context",
            json={"channel": "telegram", "message_text": "fresh"},
        )

    assert response.status_code == 200
    assert response.json() == {"user_id": "telegram:stale", "memories": []}
    assert context_response.json()["context"]["speaker_state"] is None


def test_memory_context_endpoint_returns_online_context():
    with TestClient(app) as client:
        response = client.post(
            "/v1/users/telegram:123/memory/context",
            json={
                "channel": "telegram",
                "message_text": "你好",
                "message_timestamp": "2026-06-22T06:46:00+00:00",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "telegram:123",
        "context": {
            "speaker_state": None,
            "recent_current_events": [],
            "compressed_events": [],
            "known_characters": [],
        },
    }


def test_memory_turn_endpoint_updates_online_memory():
    with TestClient(app) as client:
        update_response = client.post(
            "/v1/users/telegram:123/memory/turns",
            json={
                "channel": "telegram",
                "message_text": "有点饿了",
                "message_timestamp": "2026-06-22T09:22:00+00:00",
                "assistant_reply": "要不要先吃点简单的？",
            },
        )
        context_response = client.post(
            "/v1/users/telegram:123/memory/context",
            json={
                "channel": "telegram",
                "message_text": "还想吃甜的",
                "message_timestamp": "2026-06-22T09:25:00+00:00",
            },
        )

    assert update_response.status_code == 200
    assert update_response.json()["updated"] is True
    assert context_response.status_code == 200
    assert context_response.json()["context"]["speaker_state"]["recent_events"] == [
        "2026-06-22T09:22:00+00:00 via telegram: user said: 有点饿了 | Karen replied: 要不要先吃点简单的？"
    ]


def test_memory_context_endpoint_filters_future_turns_for_earlier_timestamp():
    with TestClient(app) as client:
        update_response = client.post(
            "/v1/users/telegram:123/memory/turns",
            json={
                "channel": "telegram",
                "message_text": "晚上一起吃饭",
                "message_timestamp": "2026-06-22T10:05:00+00:00",
                "assistant_reply": "好，我记住了。",
            },
        )
        context_response = client.post(
            "/v1/users/telegram:123/memory/context",
            json={
                "channel": "telegram",
                "message_text": "早上在忙什么",
                "message_timestamp": "2026-06-22T09:00:00+00:00",
            },
        )

    assert update_response.status_code == 200
    assert context_response.status_code == 200
    assert context_response.json()["context"] == {
        "speaker_state": None,
        "recent_current_events": [],
        "compressed_events": [],
        "known_characters": [],
    }
