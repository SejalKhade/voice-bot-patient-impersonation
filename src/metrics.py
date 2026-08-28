"""
Deterministic metrics.

Nothing in this file asks a model anything. Every number here is counted or
measured from the call log, which means it cannot hallucinate and it is
reproducible from the same transcript forever.

This separation matters. When a reviewer asks "how do you know the bot held
a real conversation", the answer should be a turn count and a latency
distribution, not a model's opinion that the call went well.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, asdict
from typing import Any

from .scenarios import Scenario
from .transcript import AGENT, PATIENT, Transcript


@dataclass
class CallMetrics:
    call_id: str
    scenario_id: str

    duration_seconds: float
    total_turns: int
    agent_turns: int
    patient_turns: int
    exchanges: int                  # completed agent-then-caller pairs

    median_response_latency: float | None
    p90_response_latency: float | None
    max_response_latency: float | None

    barge_in_count: int
    interrupted_turns: int
    tts_errors: int
    watchdog_triggered: bool

    mean_stt_confidence: float | None
    low_confidence_turns: int       # agent turns transcribed below 0.7

    probe_coverage: float
    termination_reason: str
    recording_available: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute(transcript: Transcript, scenario: Scenario) -> CallMetrics:
    latencies = [
        t.response_latency
        for t in transcript.turns
        if t.speaker == PATIENT and t.response_latency is not None and t.response_latency > 0
    ]
    confidences = [t.confidence for t in transcript.agent_turns() if t.confidence is not None]

    coverage = 0.0
    for event in transcript.events:
        if event.kind == "probe_coverage":
            try:
                coverage = float(event.detail.split("%")[0]) / 100.0
            except (ValueError, IndexError):
                coverage = 0.0

    return CallMetrics(
        call_id=transcript.call_id,
        scenario_id=transcript.scenario_id,
        duration_seconds=round(transcript.duration_seconds(), 1),
        total_turns=len(transcript.turns),
        agent_turns=len(transcript.agent_turns()),
        patient_turns=len(transcript.patient_turns()),
        exchanges=_count_exchanges(transcript),
        median_response_latency=round(statistics.median(latencies), 2) if latencies else None,
        p90_response_latency=round(_percentile(latencies, 90), 2) if latencies else None,
        max_response_latency=round(max(latencies), 2) if latencies else None,
        barge_in_count=sum(1 for e in transcript.events if e.kind == "barge_in"),
        interrupted_turns=sum(1 for t in transcript.turns if t.interrupted),
        tts_errors=sum(1 for e in transcript.events if e.kind == "tts_error"),
        watchdog_triggered=any(e.kind == "watchdog" for e in transcript.events),
        mean_stt_confidence=round(statistics.mean(confidences), 3) if confidences else None,
        low_confidence_turns=sum(1 for c in confidences if c < 0.7),
        probe_coverage=round(coverage, 2),
        termination_reason=transcript.termination_reason or "unknown",
        recording_available=bool(transcript.recording_path),
    )


def _count_exchanges(transcript: Transcript) -> int:
    """An exchange is an agent turn followed by a caller turn. Real back-and-forth."""
    count = 0
    previous = None
    for turn in transcript.turns:
        if previous == AGENT and turn.speaker == PATIENT:
            count += 1
        previous = turn.speaker
    return count


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (p / 100)
    lower, upper = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (k - lower)


# ---------------------------------------------------------------------------
# Simulator quality
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    name: str
    description: str
    measured: str
    threshold: str
    passed: bool
    weight: int
    points: int


VIABILITY_GATE_TOTAL = 100


def simulator_quality(metrics: CallMetrics) -> tuple[int, list[GateResult]]:
    """
    Score how well the harness itself performed on this call.

    This is self-QA, kept strictly apart from the agent's score. The
    assessment states that submissions whose bot cannot hold a coherent
    voice conversation are rejected before anything else is reviewed, so
    this needs to be measurable rather than assumed. A call scoring below
    about 60 here should be re-run, not analysed.
    """
    gates: list[GateResult] = []

    def gate(name: str, description: str, measured: str, threshold: str, passed: bool, weight: int) -> None:
        gates.append(
            GateResult(
                name=name,
                description=description,
                measured=measured,
                threshold=threshold,
                passed=passed,
                weight=weight,
                points=weight if passed else 0,
            )
        )

    gate(
        "Conversation depth",
        "A real conversation, not a question and a hangup.",
        f"{metrics.exchanges} exchanges",
        "at least 3",
        metrics.exchanges >= 3,
        25,
    )
    gate(
        "Call duration",
        "Long enough to exercise the scenario.",
        f"{metrics.duration_seconds:.0f}s",
        "45s to 240s",
        45 <= metrics.duration_seconds <= 240,
        15,
    )
    gate(
        "Response latency",
        "Median caller reply delay stays inside natural conversational range.",
        f"{metrics.median_response_latency:.2f}s" if metrics.median_response_latency is not None else "not measured",
        "at or below 2.50s",
        metrics.median_response_latency is not None and metrics.median_response_latency <= 2.5,
        20,
    )
    gate(
        "Scenario coverage",
        "The caller actually raised the points the scenario exists to test.",
        f"{metrics.probe_coverage:.0%}",
        "at least 60%",
        metrics.probe_coverage >= 0.6,
        20,
    )
    gate(
        "Transcription quality",
        "Agent speech was captured reliably enough to cite as evidence.",
        f"{metrics.mean_stt_confidence:.3f}" if metrics.mean_stt_confidence is not None else "not measured",
        "at or above 0.750",
        metrics.mean_stt_confidence is not None and metrics.mean_stt_confidence >= 0.75,
        10,
    )
    gate(
        "Audio pipeline health",
        "No synthesis failures during the call.",
        f"{metrics.tts_errors} errors",
        "zero",
        metrics.tts_errors == 0,
        10,
    )

    return sum(g.points for g in gates), gates
