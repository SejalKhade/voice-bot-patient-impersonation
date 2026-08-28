"""
Ground truth, and the honest handling of its absence.

The single easiest way for a QA harness like this to produce confident
nonsense is to let a model assert that the agent said something false when
the harness has no idea what the truth is. "The agent booked a Sunday
appointment but the practice is closed at weekends" is only a bug if the
practice really is closed at weekends. Without that fact on file, the
statement is a guess wearing a bug report's clothing.

So claims split into two kinds:

  Behavioural    checkable from the transcript alone. Did it contradict
                 itself? Did it ignore a stated constraint? Did it promise
                 a callback and never name a time? The transcript is
                 sufficient evidence.

  Factual        needs an external fact. Office hours, accepted insurers,
                 copay amounts, clinician names, addresses.

Behavioural claims are scored. Factual claims are only scored when the
matching fact exists in `ground_truth.yaml`. Otherwise they are quarantined
and reported as unverifiable, with the missing fact named so the reviewer
can supply it and re-run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FACT_KEYS = [
    "office_hours",
    "closed_days",
    "address",
    "phone",
    "accepted_insurers",
    "copay_amounts",
    "providers",
    "services",
    "refill_turnaround",
    "cancellation_policy",
]


@dataclass
class GroundTruth:
    facts: dict[str, Any] = field(default_factory=dict)
    source: str = "none"

    @property
    def available(self) -> bool:
        return bool(self.facts)

    def known_keys(self) -> list[str]:
        return [k for k in FACT_KEYS if self.facts.get(k)]

    def missing_keys(self) -> list[str]:
        return [k for k in FACT_KEYS if not self.facts.get(k)]

    def supports(self, key: str) -> bool:
        return bool(self.facts.get(key))

    def render(self) -> str:
        """Rendered into the analyst prompt. Empty renders as an explicit warning."""
        if not self.facts:
            return (
                "NO GROUND TRUTH IS ON FILE.\n"
                "You do not know this practice's hours, address, accepted insurers, copay "
                "amounts, providers or policies. You must not assert that any factual "
                "statement the agent made is wrong. If a finding depends on such a fact, "
                "mark it factual and name the fact you would need."
            )
        lines = ["VERIFIED FACTS ABOUT THIS PRACTICE:"]
        for key in FACT_KEYS:
            value = self.facts.get(key)
            if value:
                lines.append(f"- {key}: {value}")
        lines.append(
            "\nAnything not listed above is unknown to you. Do not assert it either way."
        )
        return "\n".join(lines)


def load(path: str | Path) -> GroundTruth:
    file = Path(path)
    if not file.exists():
        return GroundTruth(facts={}, source="none")
    try:
        import yaml

        data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return GroundTruth(facts={}, source=f"unreadable: {file}")
    if not isinstance(data, dict):
        return GroundTruth(facts={}, source=f"malformed: {file}")
    cleaned = {k: v for k, v in data.items() if v not in (None, "", [], {})}
    return GroundTruth(facts=cleaned, source=str(file))
