"""
Transcript model.

Every finding the system produces has to point at a specific turn index and
quote it verbatim. That only works if turn indices are stable and assigned
once, at capture time, in the order things were actually said. Nothing
downstream is allowed to renumber, merge or reorder turns.

Speaker attribution is structural rather than inferred. The bot generates
the caller audio itself, so it knows what it said; anything arriving on the
inbound Twilio track is the far-end agent. No diarisation, no guessing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

AGENT = "AGENT"
PATIENT = "PATIENT"
SYSTEM = "SYSTEM"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalise(text: str) -> str:
    """
    Canonical form used for verbatim evidence matching.

    Lowercase, collapse whitespace, strip punctuation that speech-to-text
    inserts inconsistently. Deliberately lossy: an adjudicator quoting
    "Sunday at 10 AM." must still match a transcript saying "sunday at 10 am".
    """
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


@dataclass
class Turn:
    index: int
    speaker: str
    text: str
    started_at: str
    ended_at: str | None = None
    # Seconds between the far end finishing and this turn's audio starting.
    # Only meaningful on PATIENT turns; it measures our own latency.
    response_latency: float | None = None
    interrupted: bool = False
    confidence: float | None = None

    def timestamp_label(self) -> str:
        try:
            return datetime.fromisoformat(self.started_at).strftime("%H:%M:%S")
        except (ValueError, TypeError):
            return "--:--:--"


@dataclass
class CallEvent:
    """Anything that happened that is not speech: barge-in, silence, errors."""

    at: str
    kind: str
    detail: str
    turn_index: int | None = None


@dataclass
class Transcript:
    call_id: str
    scenario_id: str
    scenario_title: str
    started_at: str = field(default_factory=_now)
    ended_at: str | None = None
    call_sid: str | None = None
    from_number: str | None = None
    to_number: str | None = None
    turns: list[Turn] = field(default_factory=list)
    events: list[CallEvent] = field(default_factory=list)
    recording_path: str | None = None
    termination_reason: str | None = None

    def add_turn(
        self,
        speaker: str,
        text: str,
        response_latency: float | None = None,
        interrupted: bool = False,
        confidence: float | None = None,
    ) -> Turn:
        turn = Turn(
            index=len(self.turns),
            speaker=speaker,
            text=text.strip(),
            started_at=_now(),
            response_latency=response_latency,
            interrupted=interrupted,
            confidence=confidence,
        )
        self.turns.append(turn)
        return turn

    def add_event(self, kind: str, detail: str, turn_index: int | None = None) -> None:
        self.events.append(CallEvent(at=_now(), kind=kind, detail=detail, turn_index=turn_index))

    # -- accessors used by the analysis layer ---------------------------

    def agent_turns(self) -> list[Turn]:
        return [t for t in self.turns if t.speaker == AGENT]

    def patient_turns(self) -> list[Turn]:
        return [t for t in self.turns if t.speaker == PATIENT]

    def turn(self, index: int) -> Turn | None:
        if 0 <= index < len(self.turns):
            return self.turns[index]
        return None

    def window(self, index: int, before: int = 2, after: int = 2) -> list[Turn]:
        """Neighbouring turns, used to give the adjudicator local context only."""
        low = max(0, index - before)
        high = min(len(self.turns), index + after + 1)
        return self.turns[low:high]

    def duration_seconds(self) -> float:
        if not self.ended_at:
            return 0.0
        try:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.ended_at)
            return (end - start).total_seconds()
        except (ValueError, TypeError):
            return 0.0

    def contains_verbatim(self, index: int, quote: str) -> bool:
        target = self.turn(index)
        if target is None:
            return False
        return normalise(quote) in normalise(target.text)

    def find_quote(self, quote: str) -> int | None:
        """Locate a quote anywhere in the transcript. Returns the turn index."""
        needle = normalise(quote)
        if not needle:
            return None
        for turn in self.turns:
            if needle in normalise(turn.text):
                return turn.index
        return None

    # -- serialisation ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transcript":
        turns = [Turn(**t) for t in data.pop("turns", [])]
        events = [CallEvent(**e) for e in data.pop("events", [])]
        transcript = cls(**data)
        transcript.turns = turns
        transcript.events = events
        return transcript

    def to_plaintext(self) -> str:
        lines = [
            f"Call ID       : {self.call_id}",
            f"Scenario      : {self.scenario_id} - {self.scenario_title}",
            f"Twilio SID    : {self.call_sid or 'n/a'}",
            f"From / To     : {self.from_number or 'n/a'} -> {self.to_number or 'n/a'}",
            f"Started (UTC) : {self.started_at}",
            f"Ended (UTC)   : {self.ended_at or 'n/a'}",
            f"Duration      : {self.duration_seconds():.1f}s",
            f"Turns         : {len(self.turns)}",
            f"Ended because : {self.termination_reason or 'n/a'}",
            "=" * 72,
            "",
        ]
        for turn in self.turns:
            marker = " [interrupted]" if turn.interrupted else ""
            latency = f" [+{turn.response_latency:.2f}s]" if turn.response_latency else ""
            lines.append(f"[{turn.index:03d}] {turn.timestamp_label()} {turn.speaker}{latency}{marker}")
            lines.append(f"      {turn.text}")
            lines.append("")

        if self.events:
            lines.append("=" * 72)
            lines.append("CALL EVENTS")
            lines.append("")
            for event in self.events:
                anchor = f" (turn {event.turn_index})" if event.turn_index is not None else ""
                lines.append(f"  {event.at}  {event.kind}{anchor}: {event.detail}")
        return "\n".join(lines)

    def save(self, directory: Path) -> tuple[Path, Path]:
        directory.mkdir(parents=True, exist_ok=True)
        json_path = directory / f"{self.call_id}_transcript.json"
        text_path = directory / f"{self.call_id}_transcript.txt"
        json_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        text_path.write_text(self.to_plaintext(), encoding="utf-8")
        return json_path, text_path


def load_transcript(path: Path) -> Transcript:
    return Transcript.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def render_window(turns: Iterable[Turn]) -> str:
    """Compact rendering handed to the adjudicator. Indices are preserved."""
    return "\n".join(f"[{t.index:03d}] {t.speaker}: {t.text}" for t in turns)
