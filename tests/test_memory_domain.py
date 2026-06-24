from companion_bot.memory import AgentMemory, ConversationTurn


def test_retrieve_context_is_empty_before_first_turn():
    memory = AgentMemory()

    context = memory.retrieve_context(
        ConversationTurn(
            user_id="telegram:123",
            channel="telegram",
            message_text="你好",
            message_timestamp="2026-06-22T06:46:00+00:00",
        )
    )

    assert context == {
        "speaker_state": None,
        "recent_current_events": [],
        "compressed_events": [],
        "known_characters": [],
    }


def test_update_records_user_and_karen_turn():
    memory = AgentMemory()

    update = memory.update(
        ConversationTurn(
            user_id="telegram:123",
            channel="telegram",
            message_text="有点饿了",
            message_timestamp="2026-06-22T09:22:00+00:00",
            assistant_reply="要不要先吃点简单的？",
        )
    )

    assert update["feedback_mode"] == "conversation_observation"
    assert update["updated_person"]["name"] == "user"
    assert update["updated_person"]["recent_events"] == [
        "2026-06-22T09:22:00+00:00 via telegram: user said: 有点饿了 | Karen replied: 要不要先吃点简单的？"
    ]
    assert update["added_current_event"] == {
        "time": "2026-06-22T09:22:00+00:00",
        "location": "telegram",
        "characters": ["user", "Karen"],
        "action": 'user said "有点饿了". Karen replied "要不要先吃点简单的？".',
        "known_scope": "observable_so_far",
    }


def test_retrieve_context_after_update_returns_compact_state():
    memory = AgentMemory()
    memory.update(
        ConversationTurn(
            user_id="telegram:123",
            channel="telegram",
            message_text="今天有点累",
            message_timestamp="2026-06-22T10:00:00+00:00",
            assistant_reply="那我们慢一点。",
        )
    )

    context = memory.retrieve_context(
        ConversationTurn(
            user_id="telegram:123",
            channel="telegram",
            message_text="还想聊一会儿",
            message_timestamp="2026-06-22T10:05:00+00:00",
        )
    )

    assert context["speaker_state"]["name"] == "user"
    assert context["known_characters"] == ["user"]
    assert context["recent_current_events"][-1]["action"] == (
        'user said "今天有点累". Karen replied "那我们慢一点。".'
    )


def test_retrieve_context_excludes_future_turns_for_earlier_timestamp():
    memory = AgentMemory()
    memory.update(
        ConversationTurn(
            user_id="telegram:123",
            channel="telegram",
            message_text="晚上一起吃饭",
            message_timestamp="2026-06-22T10:05:00+00:00",
            assistant_reply="好，我记住了。",
        )
    )

    context = memory.retrieve_context(
        ConversationTurn(
            user_id="telegram:123",
            channel="telegram",
            message_text="早上在忙什么",
            message_timestamp="2026-06-22T09:00:00+00:00",
        )
    )

    assert context == {
        "speaker_state": None,
        "recent_current_events": [],
        "compressed_events": [],
        "known_characters": [],
    }


def test_retrieve_context_with_invalid_timestamp_returns_empty_context():
    memory = AgentMemory()
    memory.update(
        ConversationTurn(
            user_id="telegram:123",
            channel="telegram",
            message_text="今天有点累",
            message_timestamp="2026-06-22T10:00:00+00:00",
            assistant_reply="那我们慢一点。",
        )
    )

    context = memory.retrieve_context(
        ConversationTurn(
            user_id="telegram:123",
            channel="telegram",
            message_text="继续聊",
            message_timestamp="not-a-timestamp",
        )
    )

    assert context == {
        "speaker_state": None,
        "recent_current_events": [],
        "compressed_events": [],
        "known_characters": [],
    }


def test_retrieve_context_without_timestamp_keeps_online_semantics():
    memory = AgentMemory()
    memory.update(
        ConversationTurn(
            user_id="telegram:123",
            channel="telegram",
            message_text="今天有点累",
            message_timestamp="2026-06-22T10:00:00+00:00",
            assistant_reply="那我们慢一点。",
        )
    )

    context = memory.retrieve_context(
        ConversationTurn(
            user_id="telegram:123",
            channel="telegram",
            message_text="继续聊",
        )
    )

    assert context["speaker_state"]["recent_events"] == [
        "2026-06-22T10:00:00+00:00 via telegram: user said: 今天有点累 | Karen replied: 那我们慢一点。"
    ]
    assert context["recent_current_events"][-1]["action"] == (
        'user said "今天有点累". Karen replied "那我们慢一点。".'
    )


def test_current_events_are_compressed_after_limit():
    memory = AgentMemory(max_current_events=2)

    for index in range(4):
        memory.update(
            ConversationTurn(
                user_id="telegram:123",
                channel="telegram",
                message_text=f"message {index}",
                message_timestamp=f"2026-06-22T10:0{index}:00+00:00",
                assistant_reply=f"reply {index}",
            )
        )

    data = memory.to_dict()
    assert len(data["current_events"]) == 2
    assert len(data["compressed_events"]) == 2
    assert data["compressed_events"][-1]["known_scope"] == "compressed_from_observed_history"


def test_to_dict_includes_observed_turns_needed_for_timestamp_replay():
    memory = AgentMemory()
    memory.update(
        ConversationTurn(
            user_id="telegram:123",
            channel="telegram",
            message_text="今天有点累",
            message_timestamp="2026-06-22T10:00:00+00:00",
            assistant_reply="那我们慢一点。",
        )
    )

    data = memory.to_dict()

    assert data["observed_turns"] == [
        {
            "user_id": "telegram:123",
            "channel": "telegram",
            "message_text": "今天有点累",
            "message_timestamp": "2026-06-22T10:00:00+00:00",
            "assistant_reply": "那我们慢一点。",
        }
    ]
