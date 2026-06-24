from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ConversationTurn:
    user_id: str
    channel: str
    message_text: str
    message_timestamp: str | None = None
    assistant_reply: str | None = None


@dataclass
class PersonState:
    name: str
    goals: list[str] = field(default_factory=list)
    needs: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    recent_events: list[str] = field(default_factory=list)
    behavior_patterns: list[str] = field(default_factory=list)
    interpretation_patterns: list[str] = field(default_factory=list)
    traits_or_notes: list[str] = field(default_factory=list)
    relationships: dict[str, str] = field(default_factory=dict)

    def compact(self, max_items: int = 5) -> dict[str, Any]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, list):
                data[key] = value[-max_items:]
        return data


@dataclass
class EventMemory:
    time: str
    location: str
    characters: list[str]
    action: str
    known_scope: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentMemory:
    people: dict[str, PersonState] = field(default_factory=dict)
    current_events: list[EventMemory] = field(default_factory=list)
    compressed_events: list[EventMemory] = field(default_factory=list)
    observed_turns: list[ConversationTurn] = field(default_factory=list, repr=False)
    max_current_events: int = 8
    max_recent_events_per_person: int = 8

    def retrieve_context(self, turn: ConversationTurn) -> dict[str, Any]:
        if turn.message_timestamp is None:
            return self._context_snapshot()

        boundary = _parse_iso_timestamp(turn.message_timestamp)
        if boundary is None:
            return _empty_context()

        visible_memory = AgentMemory(
            max_current_events=self.max_current_events,
            max_recent_events_per_person=self.max_recent_events_per_person,
        )
        visible_turns = sorted(
            (
                (event_time, index, observed_turn)
                for index, observed_turn in enumerate(self.observed_turns)
                for event_time in [_parse_iso_timestamp(observed_turn.message_timestamp)]
                if event_time is not None and event_time < boundary
            ),
            key=lambda item: (item[0], item[1]),
        )
        for _, _, observed_turn in visible_turns:
            visible_memory.update(observed_turn, record_observation=False)
        return visible_memory._context_snapshot()

    def update(
        self, turn: ConversationTurn, *, record_observation: bool = True
    ) -> dict[str, Any]:
        if record_observation:
            self.observed_turns.append(turn)
        person = self.people.setdefault("user", PersonState(name="user"))
        event = EventMemory(
            time=_format_time(turn),
            location=turn.channel or "unknown channel",
            characters=_characters_for(turn),
            action=_event_action(turn),
            known_scope="observable_so_far",
        )
        self.current_events.append(event)
        compressed_now = self._compress_if_needed()
        self._update_person_state(person, turn)
        return {
            "updated_person": person.compact(),
            "added_current_event": event.to_dict(),
            "compressed_events_added": [event.to_dict() for event in compressed_now],
            "feedback_mode": "conversation_observation",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "people": {
                name: state.compact(max_items=99)
                for name, state in self.people.items()
            },
            "current_events": [event.to_dict() for event in self.current_events],
            "compressed_events": [event.to_dict() for event in self.compressed_events],
            "observed_turns": [asdict(turn) for turn in self.observed_turns],
        }

    def _context_snapshot(self) -> dict[str, Any]:
        speaker_state = self.people.get("user")
        return {
            "speaker_state": speaker_state.compact() if speaker_state else None,
            "recent_current_events": [event.to_dict() for event in self.current_events[-5:]],
            "compressed_events": [event.to_dict() for event in self.compressed_events[-5:]],
            "known_characters": sorted(self.people.keys()),
        }

    def _compress_if_needed(self) -> list[EventMemory]:
        if len(self.current_events) <= self.max_current_events:
            return []

        overflow = self.current_events[: -self.max_current_events]
        self.current_events = self.current_events[-self.max_current_events :]
        speakers = sorted({name for event in overflow for name in event.characters})
        summary = "; ".join(event.action for event in overflow)
        compressed = EventMemory(
            time=f"{overflow[0].time}..{overflow[-1].time}",
            location=overflow[-1].location,
            characters=speakers,
            action=f"Compressed prior events: {summary}",
            known_scope="compressed_from_observed_history",
        )
        self.compressed_events.append(compressed)
        return [compressed]

    def _update_person_state(self, person: PersonState, turn: ConversationTurn) -> None:
        person.recent_events.append(_recent_event_note(turn))
        person.recent_events = person.recent_events[-self.max_recent_events_per_person :]


def _format_time(turn: ConversationTurn) -> str:
    return turn.message_timestamp or "current"


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _empty_context() -> dict[str, Any]:
    return {
        "speaker_state": None,
        "recent_current_events": [],
        "compressed_events": [],
        "known_characters": [],
    }


def _characters_for(turn: ConversationTurn) -> list[str]:
    if turn.assistant_reply:
        return ["user", "Karen"]
    return ["user"]


def _event_action(turn: ConversationTurn) -> str:
    action = f'user said "{turn.message_text}".'
    if turn.assistant_reply:
        action += f' Karen replied "{turn.assistant_reply}".'
    return action


def _recent_event_note(turn: ConversationTurn) -> str:
    note = f"{_format_time(turn)} via {turn.channel}: user said: {turn.message_text}"
    if turn.assistant_reply:
        note += f" | Karen replied: {turn.assistant_reply}"
    return note
