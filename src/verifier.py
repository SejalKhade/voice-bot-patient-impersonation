"""
The hallucination guard.

Every candidate finding passes through four gates in order. A candidate
that fails any gate stops there and contributes zero to the score. The full
gate trail is retained on the finding, so the dashboard can show exactly
why anything survived or died. Nothing is discarded silently.

  Gate 1  Structure          already applied in analyzer.py. Field presence,
                             turn index in range, AGENT turn, severity and
                             dimension from the allowed sets.

  Gate 2  Evidence grounding no model. The quote is normalised and matched
                             against the cited turn. If it is not there, the
                             finding was built on words nobody said.

  Gate 3  Fact dependency    a factual claim needs the matching fact on
                             file. Absent, the finding is quarantined as
                             unverifiable rather than scored. This is the
                             gate that stops the system inventing office
                             hours it has never been told.

  Gate 4  Adjudication       an independent model sees only the quote and a
                             narrow window of surrounding turns. It does not
                             see the analyst's reasoning, its severity, or
                             its framing, so it cannot simply agree with a
                             confident-sounding argument. It is sampled
                             several times; disagreement between samples is
                             treated as instability and discounts confidence.

Final confidence multiplies the adjudicator's own confidence by the
agreement rate across samples. A claim that three independent samples all
call SUPPORTED at 0.9 lands at 0.90. A claim two samples support and one
does not lands at 0.60 and may fall below threshold. That is the intended
behaviour: contested claims should not move a score as much as clear ones.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, asdict
from typing import Any

import httpx

from .analyzer import Finding
from .config import ModelConfig
from .ground_truth import GroundTruth
from .transcript import Transcript, normalise, render_window

log = logging.getLogger(__name__)

ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

CONFIDENCE_THRESHOLD = 0.55

STATUS_VERIFIED = "verified"
STATUS_UNVERIFIED = "unverified"
STATUS_REJECTED = "rejected"
STATUS_QUARANTINED = "quarantined"

ADJUDICATOR_SYSTEM = """You are an independent adjudicator. Another system has claimed that an \
AI phone agent behaved defectively. You decide whether the transcript excerpt actually \
supports that claim.

You are checking evidence, not agreeing with an argument. You have not been shown the other \
system's reasoning and you should not try to reconstruct it.

Answer SUPPORTED only if the excerpt itself shows the described behaviour.
Answer NOT_SUPPORTED if the excerpt shows something different, or shows the agent behaving acceptably.
Answer INSUFFICIENT if you would need information outside the excerpt to decide, including any \
fact about the practice that is not stated in the excerpt.

Being unsure is a correct answer. Prefer INSUFFICIENT over guessing.

Return ONLY a JSON object. No commentary, no code fences."""

ADJUDICATOR_USER = """CLAIM: {claim}

CITED QUOTE (attributed to the agent at turn {turn_index}):
"{quote}"

TRANSCRIPT EXCERPT (this is all you may rely on):
{window}

Return JSON in exactly this shape:
{{
  "verdict": "SUPPORTED",
  "confidence": 0.85,
  "reasoning": "one or two sentences, referring only to the excerpt"
}}

confidence is your own certainty in the verdict, between 0.0 and 1.0."""


@dataclass
class Gate:
    number: int
    name: str
    passed: bool
    detail: str
    evidence: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Verification:
    status: str
    confidence: float
    gates: list[Gate]
    adjudicator_votes: list[dict[str, Any]]
    agreement_rate: float
    summary: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "confidence": round(self.confidence, 3),
            "gates": [g.as_dict() for g in self.gates],
            "adjudicator_votes": self.adjudicator_votes,
            "agreement_rate": round(self.agreement_rate, 3),
            "summary": self.summary,
        }


class Verifier:
    def __init__(self, api_key: str, models: ModelConfig, ground_truth: GroundTruth) -> None:
        self._api_key = api_key
        self._models = models
        self._ground_truth = ground_truth
        self._client = httpx.Client(timeout=httpx.Timeout(90.0, connect=10.0))

    def verify(self, finding: Finding, transcript: Transcript) -> Verification:
        gates: list[Gate] = [
            Gate(
                number=1,
                name="Structure",
                passed=True,
                detail="Schema, turn range and speaker attribution accepted at extraction.",
                evidence=f"turn {finding.turn_index}, severity {finding.severity}, dimension {finding.dimension}",
            )
        ]

        # -- Gate 2 : evidence grounding, deterministic -----------------------
        turn = transcript.turn(finding.turn_index)
        grounded = turn is not None and transcript.contains_verbatim(finding.turn_index, finding.evidence_quote)
        gates.append(
            Gate(
                number=2,
                name="Evidence grounding",
                passed=grounded,
                detail=(
                    "Quote matches the cited turn after whitespace, case and punctuation normalisation."
                    if grounded
                    else "Quote does not appear in the cited turn. The finding rests on words that were not said."
                ),
                evidence=f'needle="{normalise(finding.evidence_quote)[:120]}"',
            )
        )
        if not grounded:
            return Verification(
                status=STATUS_REJECTED,
                confidence=0.0,
                gates=gates,
                adjudicator_votes=[],
                agreement_rate=0.0,
                summary="Rejected at gate 2: cited evidence is not present in the transcript.",
            )

        # -- Gate 3 : fact dependency ----------------------------------------
        is_factual = finding.claim_type.startswith("factual")
        if is_factual:
            key = finding.required_fact or ""
            have_fact = self._ground_truth.supports(key)
            gates.append(
                Gate(
                    number=3,
                    name="Fact dependency",
                    passed=have_fact,
                    detail=(
                        f"Required fact '{key}' is on file and can be checked."
                        if have_fact
                        else f"Claim depends on '{key or 'an unnamed fact'}', which is not on file. "
                        "Scoring it would mean asserting something this system does not know."
                    ),
                    evidence=f"ground truth source: {self._ground_truth.source}",
                )
            )
            if not have_fact:
                return Verification(
                    status=STATUS_QUARANTINED,
                    confidence=0.0,
                    gates=gates,
                    adjudicator_votes=[],
                    agreement_rate=0.0,
                    summary=(
                        f"Quarantined at gate 3: needs '{key or 'an external fact'}'. "
                        "Add it to data/ground_truth.yaml and re-run analysis to score this."
                    ),
                )
        else:
            gates.append(
                Gate(
                    number=3,
                    name="Fact dependency",
                    passed=True,
                    detail="Behavioural claim. Provable from the transcript alone, no external fact required.",
                    evidence="claim_type=behavioural",
                )
            )

        # -- Gate 4 : independent adjudication --------------------------------
        window = render_window(transcript.window(finding.turn_index, before=2, after=2))
        claim = f"{finding.title}. {finding.what_happened}"
        votes = [self._adjudicate(claim, finding, window) for _ in range(self._models.adjudicator_samples)]

        verdicts = [v["verdict"] for v in votes]
        tally = Counter(verdicts)
        majority, majority_count = tally.most_common(1)[0]
        agreement = majority_count / len(votes) if votes else 0.0

        supporting = [v["confidence"] for v in votes if v["verdict"] == majority]
        mean_confidence = sum(supporting) / len(supporting) if supporting else 0.0
        final_confidence = mean_confidence * agreement if majority == "SUPPORTED" else 0.0

        gates.append(
            Gate(
                number=4,
                name="Independent adjudication",
                passed=majority == "SUPPORTED" and final_confidence >= CONFIDENCE_THRESHOLD,
                detail=(
                    f"{len(votes)} independent samples returned {dict(tally)}. "
                    f"Majority verdict {majority} at {agreement:.0%} agreement, "
                    f"mean confidence {mean_confidence:.2f}. "
                    f"Final = {mean_confidence:.2f} x {agreement:.2f} = {final_confidence:.2f} "
                    f"against a {CONFIDENCE_THRESHOLD:.2f} threshold."
                ),
                evidence=f"window turns {max(0, finding.turn_index - 2)}-{finding.turn_index + 2}",
            )
        )

        if majority != "SUPPORTED":
            return Verification(
                status=STATUS_UNVERIFIED,
                confidence=0.0,
                gates=gates,
                adjudicator_votes=votes,
                agreement_rate=agreement,
                summary=(
                    f"Adjudicator majority was {majority}. Reported for the reviewer's attention "
                    "but contributes nothing to the score."
                ),
            )

        if final_confidence < CONFIDENCE_THRESHOLD:
            return Verification(
                status=STATUS_UNVERIFIED,
                confidence=round(final_confidence, 3),
                gates=gates,
                adjudicator_votes=votes,
                agreement_rate=agreement,
                summary=(
                    f"Supported but unstable: {final_confidence:.2f} falls below the "
                    f"{CONFIDENCE_THRESHOLD:.2f} threshold. Contributes nothing to the score."
                ),
            )

        return Verification(
            status=STATUS_VERIFIED,
            confidence=round(final_confidence, 3),
            gates=gates,
            adjudicator_votes=votes,
            agreement_rate=agreement,
            summary=f"Verified at {final_confidence:.2f} confidence across all four gates.",
        )

    def _adjudicate(self, claim: str, finding: Finding, window: str) -> dict[str, Any]:
        try:
            response = self._client.post(
                ANTHROPIC_ENDPOINT,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self._models.adjudicator,
                    "max_tokens": self._models.adjudicator_max_tokens,
                    # claude-sonnet-5 rejects `temperature` outright (400,
                    # "deprecated for this model"), so adjudicator_temperature
                    # goes unused here. The stability signal (see gate 4 in
                    # CONTEXT.md) now reflects this model's own default sample
                    # variance rather than a tuned value.
                    "system": ADJUDICATOR_SYSTEM,
                    "messages": [
                        {
                            "role": "user",
                            "content": ADJUDICATOR_USER.format(
                                claim=claim,
                                turn_index=finding.turn_index,
                                quote=finding.evidence_quote,
                                window=window,
                            ),
                        }
                    ],
                },
            )
            response.raise_for_status()
            raw = "".join(
                b.get("text", "") for b in response.json().get("content", []) if b.get("type") == "text"
            ).strip()
            parsed = _extract(raw)
            if parsed is None:
                return {"verdict": "INSUFFICIENT", "confidence": 0.0, "reasoning": "Unparseable adjudicator response."}

            verdict = str(parsed.get("verdict", "INSUFFICIENT")).upper().strip()
            if verdict not in {"SUPPORTED", "NOT_SUPPORTED", "INSUFFICIENT"}:
                verdict = "INSUFFICIENT"
            try:
                confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.0))))
            except (TypeError, ValueError):
                confidence = 0.0
            return {
                "verdict": verdict,
                "confidence": confidence,
                "reasoning": str(parsed.get("reasoning", "")).strip(),
            }
        except Exception as exc:  # noqa: BLE001
            log.warning("Adjudication call failed: %s", exc)
            # A failed call must never be read as agreement.
            return {"verdict": "INSUFFICIENT", "confidence": 0.0, "reasoning": f"Adjudicator error: {exc}"}

    def close(self) -> None:
        self._client.close()


def _extract(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
