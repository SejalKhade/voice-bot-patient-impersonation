"""
Tests for the parts that must be right for the rest to mean anything.

Not exhaustive coverage. These target the three places where a silent bug
would invalidate the output rather than merely break it: the audio codec
(wrong here and every call is unintelligible), evidence matching (wrong here
and the hallucination guard stops guarding), and the scoring arithmetic
(wrong here and every number on the dashboard is a lie).
"""

from __future__ import annotations

import numpy as np
import pytest

from src import audio
from src.analyzer import Finding, _structural_problem
from src.metrics import CallMetrics, simulator_quality
from src.scoring import BASE_SCORE, DIMENSION_WEIGHTS, SEVERITY_WEIGHTS, score_call
from src.transcript import AGENT, PATIENT, Transcript, normalise


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------


def test_mulaw_roundtrip_is_close_enough_for_speech():
    original = (np.sin(np.linspace(0, 40 * np.pi, 8000)) * 12000).astype(np.int16)
    recovered = audio.mulaw_to_pcm16(audio.pcm16_to_mulaw(original))

    assert len(recovered) == len(original)
    # mu-law is lossy by design. What matters is that the error stays small
    # relative to the signal, not that it is zero.
    error = np.abs(recovered.astype(np.int32) - original.astype(np.int32))
    assert error.mean() < 260, f"mean absolute error {error.mean():.1f} is too high"


def test_mulaw_preserves_sign():
    samples = np.array([-20000, -1000, -1, 0, 1, 1000, 20000], dtype=np.int16)
    recovered = audio.mulaw_to_pcm16(audio.pcm16_to_mulaw(samples))
    for original, result in zip(samples, recovered):
        if abs(int(original)) > 100:
            assert np.sign(int(result)) == np.sign(int(original))


def test_frames_are_exactly_twilio_sized():
    payload = b"\x00" * 500  # deliberately not a multiple of 160
    produced = list(audio.frames(payload))
    assert all(len(f) == audio.FRAME_BYTES for f in produced)
    assert len(produced) == 4  # 500 bytes pads out to four 160-byte frames


def test_downsample_reduces_rate_proportionally():
    source = (np.sin(np.linspace(0, 100 * np.pi, 24000)) * 8000).astype(np.int16)
    result = audio.downsample_pcm16(source, 24000, 8000)
    assert abs(len(result) - 8000) <= 2


def test_base64_frame_roundtrip():
    frame = bytes(range(160))
    assert audio.decode_payload(audio.encode_frame(frame)) == frame


# ---------------------------------------------------------------------------
# Evidence matching
# ---------------------------------------------------------------------------


def _transcript() -> Transcript:
    t = Transcript(call_id="test_01", scenario_id="S04", scenario_title="Weekend request")
    t.add_turn(PATIENT, "Hi, can I come in on Sunday at ten?")
    t.add_turn(AGENT, "Sure, I've scheduled you for Sunday at 10 AM.")
    t.add_turn(PATIENT, "Great, thanks.")
    t.add_turn(AGENT, "Is there anything else I can help with today?")
    return t


def test_normalisation_ignores_case_and_punctuation():
    assert normalise("Sunday at 10 AM.") == normalise("sunday at 10 am")


def test_verbatim_match_tolerates_formatting_but_not_invention():
    t = _transcript()
    assert t.contains_verbatim(1, "scheduled you for Sunday at 10 AM")
    assert t.contains_verbatim(1, "Scheduled you for sunday at 10 am.")
    assert not t.contains_verbatim(1, "scheduled you for Monday at 10 AM")


def test_fabricated_quote_is_discarded():
    t = _transcript()
    problem = _structural_problem(
        {
            "title": "Books on a closed day",
            "turn_index": 1,
            "evidence_quote": "Our clinic is open every day of the week",
            "claim_type": "behavioural",
            "severity": "high",
            "dimension": "task_completion",
        },
        t,
    )
    assert problem is not None and "does not appear" in problem


def test_finding_citing_a_caller_turn_is_relocated_or_rejected():
    t = _transcript()
    candidate = {
        "title": "Books on a closed day",
        "turn_index": 0,  # a PATIENT turn
        "evidence_quote": "I've scheduled you for Sunday at 10 AM",
        "claim_type": "behavioural",
        "severity": "high",
        "dimension": "task_completion",
    }
    # The quote genuinely exists in an AGENT turn, so it is relocated rather
    # than thrown away. Being strict about the index but forgiving about
    # an off-by-one keeps real bugs from being lost to a citation slip.
    assert _structural_problem(candidate, t) is None
    assert candidate["turn_index"] == 1


def test_unknown_severity_is_rejected():
    t = _transcript()
    problem = _structural_problem(
        {
            "title": "x",
            "turn_index": 1,
            "evidence_quote": "scheduled you for Sunday",
            "claim_type": "behavioural",
            "severity": "catastrophic",
            "dimension": "task_completion",
        },
        t,
    )
    assert problem is not None and "severity" in problem


def test_out_of_range_turn_is_rejected():
    t = _transcript()
    problem = _structural_problem(
        {
            "title": "x",
            "turn_index": 99,
            "evidence_quote": "anything",
            "claim_type": "behavioural",
            "severity": "low",
            "dimension": "task_completion",
        },
        t,
    )
    assert problem is not None and "outside the transcript" in problem


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _metrics(**overrides) -> CallMetrics:
    defaults = dict(
        call_id="test_01",
        scenario_id="S04",
        duration_seconds=95.0,
        total_turns=12,
        agent_turns=6,
        patient_turns=6,
        exchanges=6,
        median_response_latency=1.4,
        p90_response_latency=2.1,
        max_response_latency=2.4,
        barge_in_count=1,
        interrupted_turns=1,
        tts_errors=0,
        watchdog_triggered=False,
        mean_stt_confidence=0.93,
        low_confidence_turns=0,
        probe_coverage=1.0,
        termination_reason="caller:objective-resolved",
        recording_available=True,
    )
    defaults.update(overrides)
    return CallMetrics(**defaults)


def _finding(severity: str, dimension: str, confidence: float, status: str = "verified") -> Finding:
    finding = Finding(
        id="test_01-F01",
        call_id="test_01",
        scenario_id="S04",
        title="Test finding",
        turn_index=1,
        evidence_quote="scheduled you for Sunday",
        claim_type="behavioural",
        required_fact=None,
        severity=severity,
        dimension=dimension,
        what_happened="",
        why_it_matters="",
        expected_behaviour="",
    )
    finding.verification = {"status": status, "confidence": confidence, "summary": ""}
    return finding


def test_clean_call_scores_full_simulator_marks():
    score, gates = simulator_quality(_metrics())
    assert score == 100
    assert all(g.passed for g in gates)


def test_single_question_hangup_fails_the_depth_gate():
    score, gates = simulator_quality(_metrics(exchanges=1, duration_seconds=14.0, probe_coverage=0.2))
    depth = next(g for g in gates if g.name == "Conversation depth")
    assert not depth.passed
    assert score < 60  # below the "not usable" line


def test_deduction_is_severity_times_confidence():
    finding = _finding("high", "task_completion", 0.80)
    score = score_call(_metrics(), [finding])

    dimension = next(d for d in score.dimension_scores if d.dimension == "task_completion")
    expected = BASE_SCORE - SEVERITY_WEIGHTS["high"] * 0.80  # 100 - 12.0
    assert dimension.score == pytest.approx(expected, abs=0.01)
    assert "15 x 0.80 = -12.00" in dimension.deductions[0].expression


def test_unverified_findings_deduct_nothing():
    verified = score_call(_metrics(), [_finding("critical", "safety_and_escalation", 0.9, "verified")])
    unverified = score_call(_metrics(), [_finding("critical", "safety_and_escalation", 0.9, "unverified")])

    assert unverified.agent_score > verified.agent_score
    assert unverified.agent_score == pytest.approx(100.0, abs=0.01)
    assert unverified.counts["verified"] == 0


def test_quarantined_findings_deduct_nothing_but_are_listed():
    score = score_call(_metrics(), [_finding("high", "information_accuracy", 0.0, "quarantined")])
    assert score.agent_score == pytest.approx(100.0, abs=0.01)
    assert len(score.excluded) == 1
    assert score.excluded[0]["status"] == "quarantined"


def test_composite_is_the_weighted_sum_of_dimensions():
    score = score_call(_metrics(), [_finding("medium", "conversational_handling", 1.0)])
    manual = sum(d.score * DIMENSION_WEIGHTS[d.dimension] for d in score.dimension_scores)
    assert score.agent_score == pytest.approx(manual, abs=0.01)


def test_dimension_score_floors_at_zero():
    findings = [_finding("critical", "safety_and_escalation", 1.0) for _ in range(6)]
    score = score_call(_metrics(), findings)
    dimension = next(d for d in score.dimension_scores if d.dimension == "safety_and_escalation")
    assert dimension.score == 0.0


def test_dimension_weights_sum_to_one():
    assert sum(DIMENSION_WEIGHTS.values()) == pytest.approx(1.0, abs=1e-9)
