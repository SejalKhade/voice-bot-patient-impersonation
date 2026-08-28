"""
The patient brain.

One design decision dominates this file: the caller is a stateful agent
with an agenda, not a script reader. The evaluation criteria for this
assessment call out "active steering of the conversation toward the
intended test-case outcome", and a fixed script cannot steer. It says line
three regardless of what it just heard, which is exactly what a scripted
benchmark runner sounds like.

So the brain tracks which probes it has landed and is told, every turn,
what is still outstanding. That keeps calls on-target without making them
robotic, because the wording is still generated fresh against whatever the
agent actually said.

Latency is the other constraint. This model sits inside the turn loop, so
it runs on a small fast model with a tight token ceiling. Anything over
about 800 ms here is audible as an unnatural gap.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

import httpx

from .config import ModelConfig
from .scenarios import Scenario

log = logging.getLogger(__name__)

ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

SYSTEM_TEMPLATE = """You are role-playing a patient telephoning a medical practice. \
The other party is an AI phone agent. You are testing it, but you must never reveal that.

Absolute rules:
- Output ONLY the words you speak aloud. No stage directions, no narration, no quotation marks, no labels.
- One to two sentences per turn. This is a phone call, not an email.
- Ask at most one question per turn.
- Never mention being an AI, a test, a bot, or a simulation. If asked directly, deflect naturally and continue.
- React to what was actually just said. If the agent asked you something, answer it before moving on.
- Speak in plain spoken English. Say numbers the way people say them out loud.
- Do not invent details about the practice. You are the caller; you only know your own situation.

Who you are:
{persona}

What you are trying to achieve on this call:
{objective}

Points you need to raise before the call ends:
{probes}

Ending the call:
When your objective is resolved, or it becomes clear it will not be, say a short natural goodbye \
and include the exact word GOODBYE somewhere in that final sentence.
{modifiers}"""


@dataclass
class PatientState:
    turn_count: int = 0
    probes_landed: list[int] = field(default_factory=list)
    wants_to_end: bool = False
    last_latency: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class PatientBrain:
    def __init__(self, scenario: Scenario, api_key: str, models: ModelConfig) -> None:
        self._scenario = scenario
        self._api_key = api_key
        self._models = models
        self._history: list[dict] = []
        self.state = PatientState()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0))

    # -- prompt construction ---------------------------------------------

    def _modifiers(self) -> str:
        lines: list[str] = []
        if self._scenario.interrupt_agent:
            lines.append(
                "- You are impatient. Keep your turns very short and cut in as soon as you have heard enough."
            )
        if self._scenario.speak_slowly:
            lines.append(
                "- You speak haltingly. Use simple words, short clauses, and occasional self-corrections."
            )
        if self._scenario.inject_silence:
            lines.append(
                "- You are distracted and on a poor line. Occasionally answer as if you missed part of what was said."
            )
        if not lines:
            return ""
        return "\n\nHow you speak:\n" + "\n".join(lines)

    def _system_prompt(self) -> str:
        probes = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(self._scenario.probes))
        return SYSTEM_TEMPLATE.format(
            persona=self._scenario.persona,
            objective=self._scenario.objective,
            probes=probes,
            modifiers=self._modifiers(),
        )

    def _steering_note(self) -> str:
        """
        Injected each turn so the caller keeps its own agenda in view.

        This is the mechanism that turns a chatty role-player into a test
        case that actually completes. Without it, calls wander pleasantly
        and land maybe half the probes.
        """
        outstanding = [
            f"{i + 1}. {probe}"
            for i, probe in enumerate(self._scenario.probes)
            if i not in self.state.probes_landed
        ]
        if not outstanding:
            return "(All your points have been raised. Wrap the call up naturally when it makes sense.)"
        remaining_turns = max(1, 14 - self.state.turn_count)
        return (
            "(Still to raise:\n"
            + "\n".join(outstanding)
            + f"\nRoughly {remaining_turns} turns left. Work these in naturally; do not list them.)"
        )

    # -- turn generation ---------------------------------------------------

    async def opening_line(self) -> str:
        text = await self._generate(
            "The agent has just answered the phone and greeted you. Say your opening line."
        )
        return text

    async def reply_to(self, agent_said: str) -> str:
        text = await self._generate(f'The agent said: "{agent_said}"\n\n{self._steering_note()}')
        return text

    async def _generate(self, user_content: str) -> str:
        self._history.append({"role": "user", "content": user_content})
        started = time.monotonic()

        payload = {
            "model": self._models.patient,
            "max_tokens": self._models.patient_max_tokens,
            "temperature": self._models.patient_temperature,
            "system": self._system_prompt(),
            "messages": self._history,
        }

        text = ""
        for attempt in range(3):
            try:
                response = await self._client.post(
                    ANTHROPIC_ENDPOINT,
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": ANTHROPIC_VERSION,
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    await asyncio.sleep(0.6 * (attempt + 1))
                    continue
                response.raise_for_status()
                body = response.json()
                text = "".join(
                    block.get("text", "") for block in body.get("content", []) if block.get("type") == "text"
                ).strip()
                usage = body.get("usage", {})
                self.state.total_input_tokens += usage.get("input_tokens", 0)
                self.state.total_output_tokens += usage.get("output_tokens", 0)
                break
            except Exception as exc:  # noqa: BLE001
                log.warning("Patient generation attempt %d failed: %s", attempt + 1, exc)
                await asyncio.sleep(0.5 * (attempt + 1))

        if not text:
            # A silent caller is worse than a slightly generic one. Never
            # return empty into the turn loop.
            text = "Sorry, could you say that again?"

        self.state.last_latency = time.monotonic() - started
        self.state.turn_count += 1
        self._history.append({"role": "assistant", "content": text})

        cleaned = self._clean(text)
        if "GOODBYE" in text.upper():
            self.state.wants_to_end = True
        return cleaned

    @staticmethod
    def _clean(text: str) -> str:
        """Strip the sentinel and any stage directions that slipped through."""
        import re

        text = re.sub(r"\bGOODBYE\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\*[^*]*\*", "", text)      # *sighs*
        text = re.sub(r"\([^)]*\)", "", text)       # (pausing)
        text = re.sub(r"^\s*(patient|caller)\s*:\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text)
        return text.strip().strip('"')

    # -- probe tracking ------------------------------------------------------

    async def update_probe_coverage(self) -> None:
        """
        Ask the model, once, which probes the caller has already raised.

        Run out of band after the call rather than per turn, because a
        second inference inside the turn loop would double the latency
        budget. During the call, coverage is tracked optimistically by
        turn count; this pass corrects the record afterwards.
        """
        spoken = [m["content"] for m in self._history if m["role"] == "assistant"]
        if not spoken:
            return

        prompt = (
            "Here is everything a caller said during a phone call, in order:\n\n"
            + "\n".join(f"- {line}" for line in spoken)
            + "\n\nHere are the points the caller was supposed to raise:\n"
            + "\n".join(f"{i}. {p}" for i, p in enumerate(self._scenario.probes))
            + "\n\nReturn ONLY a JSON array of the zero-based indices of the points that were "
            "actually raised. No other text. Example: [0, 2]"
        )

        try:
            response = await self._client.post(
                ANTHROPIC_ENDPOINT,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self._models.patient,
                    "max_tokens": 100,
                    "temperature": 0,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            raw = "".join(
                b.get("text", "") for b in response.json().get("content", []) if b.get("type") == "text"
            ).strip()
            start, end = raw.find("["), raw.rfind("]")
            if start != -1 and end != -1:
                indices = json.loads(raw[start:end + 1])
                self.state.probes_landed = [
                    i for i in indices if isinstance(i, int) and 0 <= i < len(self._scenario.probes)
                ]
        except Exception as exc:  # noqa: BLE001
            log.warning("Probe coverage check failed: %s", exc)

    def probe_coverage(self) -> float:
        if not self._scenario.probes:
            return 1.0
        return len(set(self.state.probes_landed)) / len(self._scenario.probes)

    async def close(self) -> None:
        await self._client.aclose()
