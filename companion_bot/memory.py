from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    max_current_events: int = 8
    max_recent_events_per_person: int = 8

    def retrieve_context(self, turn: ConversationTurn) -> dict[str, Any]:
        speaker_state = self.people.get("user")
        return {
            "speaker_state": speaker_state.compact() if speaker_state else None,
            "recent_current_events": [event.to_dict() for event in self.current_events[-5:]],
            "compressed_events": [event.to_dict() for event in self.compressed_events[-5:]],
            "known_characters": sorted(self.people.keys()),
        }

    def update(self, turn: ConversationTurn) -> dict[str, Any]:
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
