from fastapi.testclient import TestClient

from companion_bot.services.memory import _memory_store, app


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

    with TestClient(app) as client:
        response = client.get("/v1/users/telegram:stale/memories")

    assert response.status_code == 200
    assert response.json() == {"user_id": "telegram:stale", "memories": []}
