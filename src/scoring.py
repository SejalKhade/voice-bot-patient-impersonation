"""
Scoring, with the arithmetic kept on the record.

Two separate scores that must never be blended:

  Simulator Quality   how well this harness performed. Measured, not judged.
  Agent Quality       how well the system under test performed. Derived only
                      from verified findings.

Mixing them would let a bad call flatter the agent, or a good harness hide
a bad agent. They answer different questions and they have different owners.

Every deduction is emitted as a `ScoreLine` carrying its own inputs and the
literal expression that produced it, for example "high: 15 x 0.82 = 12.30".
The dashboard renders those lines directly, so the displayed total is the
computed total rather than a restatement of it.

The weights below are a stated policy, not a discovered truth. They are
here to be argued with, which is why they are one dictionary at the top of
the file instead of scattered through the logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from .analyzer import DIMENSIONS, Finding
from .metrics import CallMetrics, GateResult, simulator_quality
from .verifier import STATUS_QUARANTINED, STATUS_REJECTED, STATUS_UNVERIFIED, STATUS_VERIFIED

BASE_SCORE = 100

# Deduction weight per verified finding, before the confidence multiplier.
SEVERITY_WEIGHTS = {
    "critical": 25,
    "high": 15,
    "medium": 7,
    "low": 3,
}

# Contribution of each dimension to the composite agent score.
DIMENSION_WEIGHTS = {
    "task_completion": 0.30,
    "information_accuracy": 0.25,
    "safety_and_escalation": 0.25,
    "conversational_handling": 0.12,
    "scope_and_handoff": 0.08,
}

DIMENSION_LABELS = {
    "task_completion": "Task completion",
    "information_accuracy": "Information accuracy",
    "safety_and_escalation": "Safety and escalation",
    "conversational_handling": "Conversational handling",
    "scope_and_handoff": "Scope and handoff",
}


@dataclass
class ScoreLine:
    label: str
    expression: str
    value: float
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DimensionScore:
    dimension: str
    label: str
    weight: float
    base: int
    deductions: list[ScoreLine]
    score: float
    weighted_contribution: float

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["deductions"] = [d.as_dict() for d in self.deductions]
        return data


@dataclass
class CallScore:
    call_id: str
    scenario_id: str

    simulator_score: int
    simulator_gates: list[GateResult]
    simulator_verdict: str

    agent_score: float
    dimension_scores: list[DimensionScore]
    agent_lines: list[ScoreLine]

    counts: dict[str, int]
    excluded: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "scenario_id": self.scenario_id,
            "simulator_score": self.simulator_score,
            "simulator_gates": [asdict(g) for g in self.simulator_gates],
            "simulator_verdict": self.simulator_verdict,
            "agent_score": round(self.agent_score, 2),
            "dimension_scores": [d.as_dict() for d in self.dimension_scores],
            "agent_lines": [l.as_dict() for l in self.agent_lines],
            "counts": self.counts,
            "excluded": self.excluded,
        }


def score_call(metrics: CallMetrics, findings: list[Finding]) -> CallScore:
    sim_score, sim_gates = simulator_quality(metrics)

    if sim_score >= 80:
        verdict = "Usable. Conversation quality supports the findings below."
    elif sim_score >= 60:
        verdict = "Usable with reservations. Check the failed gates before citing this call."
    else:
        verdict = "Not usable. Re-run this scenario; findings from it are unreliable."

    verified = [f for f in findings if f.verification.get("status") == STATUS_VERIFIED]
    unverified = [f for f in findings if f.verification.get("status") == STATUS_UNVERIFIED]
    quarantined = [f for f in findings if f.verification.get("status") == STATUS_QUARANTINED]
    rejected = [f for f in findings if f.verification.get("status") == STATUS_REJECTED]

    dimension_scores: list[DimensionScore] = []
    for dimension in DIMENSIONS:
        relevant = [f for f in verified if f.dimension == dimension]
        deductions: list[ScoreLine] = []
        running = float(BASE_SCORE)
        for finding in relevant:
            weight = SEVERITY_WEIGHTS.get(finding.severity, 3)
            confidence = float(finding.verification.get("confidence", 0.0))
            amount = weight * confidence
            running -= amount
            deductions.append(
                ScoreLine(
                    label=f"{finding.id} {finding.title}",
                    expression=f"{finding.severity}: {weight} x {confidence:.2f} = -{amount:.2f}",
                    value=-round(amount, 2),
                    note=f"turn {finding.turn_index}",
                )
            )
        score = max(0.0, running)
        weight = DIMENSION_WEIGHTS[dimension]
        dimension_scores.append(
            DimensionScore(
                dimension=dimension,
                label=DIMENSION_LABELS[dimension],
                weight=weight,
                base=BASE_SCORE,
                deductions=deductions,
                score=round(score, 2),
                weighted_contribution=round(score * weight, 2),
            )
        )

    agent_score = sum(d.weighted_contribution for d in dimension_scores)

    lines = [
        ScoreLine(
            label=f"{d.label} ({d.weight:.0%})",
            expression=f"{d.score:.2f} x {d.weight:.2f} = {d.weighted_contribution:.2f}",
            value=d.weighted_contribution,
            note=f"{len(d.deductions)} verified finding(s)",
        )
        for d in dimension_scores
    ]
    lines.append(
        ScoreLine(
            label="Composite agent score",
            expression=" + ".join(f"{d.weighted_contribution:.2f}" for d in dimension_scores)
            + f" = {agent_score:.2f}",
            value=round(agent_score, 2),
        )
    )

    excluded = [
        {
            "id": f.id,
            "title": f.title,
            "severity": f.severity,
            "status": f.verification.get("status"),
            "reason": f.verification.get("summary", ""),
            "would_have_deducted": round(SEVERITY_WEIGHTS.get(f.severity, 3) * DIMENSION_WEIGHTS.get(f.dimension, 0), 2),
        }
        for f in unverified + quarantined + rejected
    ]

    return CallScore(
        call_id=metrics.call_id,
        scenario_id=metrics.scenario_id,
        simulator_score=sim_score,
        simulator_gates=sim_gates,
        simulator_verdict=verdict,
        agent_score=round(agent_score, 2),
        dimension_scores=dimension_scores,
        agent_lines=lines,
        counts={
            "candidates": len(findings),
            "verified": len(verified),
            "unverified": len(unverified),
            "quarantined": len(quarantined),
            "rejected": len(rejected),
        },
        excluded=excluded,
    )


@dataclass
class RunScore:
    calls_scored: int
    mean_simulator_score: float
    mean_agent_score: float
    dimension_means: dict[str, float]
    severity_counts: dict[str, int]
    verification_counts: dict[str, int]
    hallucination_rate: float
    lines: list[ScoreLine]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["lines"] = [l.as_dict() for l in self.lines]
        return data


def score_run(call_scores: list[CallScore], all_findings: list[Finding]) -> RunScore:
    if not call_scores:
        return RunScore(0, 0.0, 0.0, {}, {}, {}, 0.0, [])

    mean_sim = sum(c.simulator_score for c in call_scores) / len(call_scores)
    mean_agent = sum(c.agent_score for c in call_scores) / len(call_scores)

    dimension_means: dict[str, float] = {}
    for dimension in DIMENSIONS:
        values = [d.score for c in call_scores for d in c.dimension_scores if d.dimension == dimension]
        dimension_means[dimension] = round(sum(values) / len(values), 2) if values else 100.0

    verified = [f for f in all_findings if f.verification.get("status") == STATUS_VERIFIED]

    severity_counts = {s: sum(1 for f in verified if f.severity == s) for s in SEVERITY_WEIGHTS}
    verification_counts = {
        status: sum(1 for f in all_findings if f.verification.get("status") == status)
        for status in (STATUS_VERIFIED, STATUS_UNVERIFIED, STATUS_QUARANTINED, STATUS_REJECTED)
    }

    # The share of candidates the guard removed. Reported openly because it
    # is the honest measure of how much the analyst overclaims, and because
    # a reviewer should be able to see that the guard is doing real work.
    total = len(all_findings)
    filtered = verification_counts[STATUS_REJECTED] + verification_counts[STATUS_UNVERIFIED]
    hallucination_rate = (filtered / total) if total else 0.0

    lines = [
        ScoreLine(
            "Mean simulator quality",
            " + ".join(str(c.simulator_score) for c in call_scores) + f" / {len(call_scores)} = {mean_sim:.2f}",
            round(mean_sim, 2),
        ),
        ScoreLine(
            "Mean agent quality",
            " + ".join(f"{c.agent_score:.1f}" for c in call_scores) + f" / {len(call_scores)} = {mean_agent:.2f}",
            round(mean_agent, 2),
        ),
        ScoreLine(
            "Candidate filter rate",
            f"({verification_counts[STATUS_REJECTED]} rejected + {verification_counts[STATUS_UNVERIFIED]} unverified)"
            f" / {total} candidates = {hallucination_rate:.1%}",
            round(hallucination_rate, 4),
            note="Share of proposed findings the guard removed before scoring.",
        ),
    ]

    return RunScore(
        calls_scored=len(call_scores),
        mean_simulator_score=round(mean_sim, 2),
        mean_agent_score=round(mean_agent, 2),
        dimension_means=dimension_means,
        severity_counts=severity_counts,
        verification_counts=verification_counts,
        hallucination_rate=round(hallucination_rate, 4),
        lines=lines,
    )
