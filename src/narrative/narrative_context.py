"""Narrative context window and lightweight compression helpers."""

from __future__ import annotations

from typing import Dict, List, Set

from pydantic import BaseModel, Field


class NarrativeEvent(BaseModel):
    """A compact event record used to maintain recent narrative context."""

    turn: int = Field(default=0)
    actor_id: str = Field(default="")
    actor_name: str = Field(default="")
    text: str = Field(default="")
    source: str = Field(default="system")
    key_facts: List[str] = Field(default_factory=list)


class NarrativeContextSnapshot(BaseModel):
    """Serializable snapshot of context state."""

    window_size: int = Field(default=5, ge=1)
    recent_events: List[NarrativeEvent] = Field(default_factory=list)
    summary_lines: List[str] = Field(default_factory=list)
    key_facts: List[str] = Field(default_factory=list)


class NarrativeContext:
    """Lightweight rolling narrative context for prompt assembly."""

    def __init__(self, window_size: int = 5, max_summary_lines: int = 100):
        self.window_size = max(1, window_size)
        self.max_summary_lines = max(1, max_summary_lines)
        self.recent_events: List[NarrativeEvent] = []
        self.summary_lines: List[str] = []
        self.summary: str = ""
        self.key_facts: Set[str] = set()

    def add_event(self, event: NarrativeEvent) -> None:
        if not event.text.strip():
            return

        self.recent_events.append(event)
        if event.key_facts:
            self.key_facts.update(f.strip() for f in event.key_facts if f.strip())
        else:
            self.key_facts.update(self._extract_key_facts(event.text))

        while len(self.recent_events) > self.window_size:
            oldest = self.recent_events.pop(0)
            self._compress_oldest(oldest)

    def get_context_for_llm(self) -> str:
        sections: List[str] = []

        if self.summary:
            sections.append(f"Summary:\n{self.summary}")

        if self.recent_events:
            recent_lines = [
                f"[Turn {event.turn}] {event.actor_name or event.actor_id or event.source}: {event.text}"
                for event in self.recent_events
            ]
            sections.append("Recent events:\n" + "\n".join(recent_lines))

        if self.key_facts:
            sections.append("Key facts:\n" + ", ".join(sorted(self.key_facts)))

        return "\n\n".join(sections)

    def to_snapshot(self) -> NarrativeContextSnapshot:
        """Build a typed snapshot for persistence boundaries."""
        return NarrativeContextSnapshot(
            window_size=self.window_size,
            recent_events=self.recent_events.copy(),
            summary_lines=self.summary_lines.copy(),
            key_facts=sorted(self.key_facts),
        )

    @classmethod
    def from_snapshot(cls, snapshot: NarrativeContextSnapshot) -> "NarrativeContext":
        """Rebuild context from a typed snapshot."""
        ctx = cls(window_size=snapshot.window_size)
        ctx.recent_events = snapshot.recent_events.copy()
        ctx.summary_lines = snapshot.summary_lines.copy()
        ctx.key_facts = set(snapshot.key_facts)
        ctx._refresh_summary_text()
        return ctx

    def export_state(self) -> Dict[str, object]:
        snapshot = self.to_snapshot()
        return {
            "window_size": snapshot.window_size,
            "recent_events": [event.model_dump() for event in snapshot.recent_events],
            "summary": self.summary,
            "summary_lines": snapshot.summary_lines,
            "key_facts": snapshot.key_facts,
        }

    def _compress_oldest(self, event: NarrativeEvent) -> None:
        compressed = self._compress_text(event.text)
        if not compressed:
            return

        actor_label = event.actor_name or event.actor_id or event.source
        line = f"[Turn {event.turn}] {actor_label}: {compressed}"
        self.summary_lines.append(line)
        if len(self.summary_lines) > self.max_summary_lines:
            self.summary_lines = self.summary_lines[-self.max_summary_lines :]
        self._refresh_summary_text()

    def _refresh_summary_text(self) -> None:
        self.summary = "\n".join(self.summary_lines).strip()

    def _compress_text(self, text: str) -> str:
        normalized = " ".join(text.split())
        if len(normalized) <= 120:
            return normalized
        return normalized[:117].rstrip() + "..."

    def _extract_key_facts(self, text: str) -> Set[str]:
        facts: Set[str] = set()
        lowered = text.lower()

        for keyword in (
            "hp",
            "san",
            "luck",
            "lucky",
            "injury",
            "wound",
            "key",
            "door",
            "clue",
            "blood",
        ):
            if keyword in lowered or keyword in text:
                facts.add(keyword)

        return facts

