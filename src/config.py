"""
Configuration objects for a run.

Credentials travel as plain dataclass fields through the process and are
never written to `data/`. The store layer strips them before serialising.
If you add a field here that holds a secret, add it to `SECRET_FIELDS` too.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any

# The assessment line. Hard-coded because dialling anything else during a
# test run is a mistake, not a feature.
TARGET_NUMBER = "+18054398008"

SECRET_FIELDS = {
    "twilio_auth_token",
    "anthropic_api_key",
    "deepgram_api_key",
    "elevenlabs_api_key",
    "openai_api_key",
}


@dataclass
class ModelConfig:
    """
    Three distinct model roles, deliberately separated.

    The patient brain is optimised for latency because it sits inside the
    turn loop. The analyst and the adjudicator are optimised for judgement
    because they run offline. Using one model for all three would either
    make calls sluggish or make analysis shallow.
    """

    patient: str = "claude-haiku-4-5-20251001"
    analyst: str = "claude-sonnet-5"
    adjudicator: str = "claude-sonnet-5"

    patient_max_tokens: int = 160
    patient_temperature: float = 0.85

    analyst_max_tokens: int = 4000
    analyst_temperature: float = 0.2

    adjudicator_max_tokens: int = 800
    # Non-zero on purpose: the adjudicator is sampled several times and the
    # spread between samples is the stability signal. At temperature 0 every
    # sample is identical and the agreement rate is meaningless.
    adjudicator_temperature: float = 0.4
    adjudicator_samples: int = 3


@dataclass
class VoiceConfig:
    provider: str = "elevenlabs"  # elevenlabs | openai
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    elevenlabs_model: str = "eleven_turbo_v2_5"
    openai_voice: str = "alloy"
    openai_model: str = "gpt-4o-mini-tts"


@dataclass
class SpeechConfig:
    model: str = "nova-2-phonecall"
    # Endpointing is the single biggest lever on how natural the bot sounds.
    # Too low and it talks over the agent's mid-sentence pauses; too high and
    # every turn carries a dead second. 320ms -> 700ms after run_20260903_063047
    # still wasn't enough: run_20260903_073903 showed 9 truncated agent turns,
    # confirmed by ear as real overlap, not just dead air. Worse, it cascades -
    # once the caller's reply to a cut-off utterance is something like "you cut
    # out, can you repeat that", the agent restarts its explanation and gets cut
    # off again, so one early misfire snowballs through most of the call.
    # Raised again; if this still isn't enough the barge-in guard likely needs
    # to also gate on whether the agent has been continuously producing speech
    # rather than trusting Deepgram's endpoint alone.
    endpointing_ms: int = 1100
    utterance_end_ms: int = 2200
    interim_results: bool = True


@dataclass
class CallPolicy:
    """Guard rails that stop a stuck call from burning telephony credit."""

    max_call_seconds: int = 240
    max_turns: int = 24
    # If the far end goes quiet for this long with no speech events, assume
    # the agent has hung up or the audio path is dead and close cleanly.
    silence_timeout_seconds: int = 18
    # Delay before the patient speaks first, so we do not clip the agent's
    # greeting. Real callers wait to be greeted.
    opening_delay_seconds: float = 1.2
    barge_in_enabled: bool = True
    inter_call_cooldown_seconds: int = 25


@dataclass
class RunConfig:
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    anthropic_api_key: str = ""
    deepgram_api_key: str = ""
    elevenlabs_api_key: str = ""
    openai_api_key: str = ""

    public_base_url: str = ""       # ngrok host, no scheme
    media_server_port: int = 8080

    target_number: str = TARGET_NUMBER

    models: ModelConfig = field(default_factory=ModelConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    speech: SpeechConfig = field(default_factory=SpeechConfig)
    policy: CallPolicy = field(default_factory=CallPolicy)

    ground_truth_path: str = "data/ground_truth.yaml"

    @classmethod
    def from_env(cls) -> "RunConfig":
        cfg = cls(
            twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
            twilio_from_number=os.getenv("TWILIO_FROM_NUMBER", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", ""),
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            public_base_url=os.getenv("PUBLIC_BASE_URL", "").replace("https://", "").replace("http://", "").rstrip("/"),
            target_number=os.getenv("TARGET_NUMBER", TARGET_NUMBER),
        )
        if os.getenv("ELEVENLABS_VOICE_ID"):
            cfg.voice.elevenlabs_voice_id = os.environ["ELEVENLABS_VOICE_ID"]
        if os.getenv("VOICE_PROVIDER"):
            cfg.voice.provider = os.environ["VOICE_PROVIDER"]
        return cfg

    def missing_requirements(self) -> list[str]:
        """Human-readable list of what still has to be filled in."""
        problems: list[str] = []
        if not self.twilio_account_sid.startswith("AC"):
            problems.append("Twilio Account SID is missing or does not start with AC")
        if not self.twilio_auth_token:
            problems.append("Twilio Auth Token is missing")
        if not self.twilio_from_number.startswith("+"):
            problems.append("Twilio phone number must be in E.164 format, for example +15551234567")
        if not self.anthropic_api_key:
            problems.append("Anthropic API key is missing")
        if not self.deepgram_api_key:
            problems.append("Deepgram API key is missing")
        if self.voice.provider == "elevenlabs" and not self.elevenlabs_api_key:
            problems.append("ElevenLabs API key is missing")
        if self.voice.provider == "openai" and not self.openai_api_key:
            problems.append("OpenAI API key is missing")
        if not self.public_base_url:
            problems.append("Public base URL is missing; start ngrok and paste the host")
        return problems

    def redacted(self) -> dict[str, Any]:
        """Serialisable copy with every secret replaced by a length marker."""
        data = asdict(self)
        for key in SECRET_FIELDS:
            value = data.get(key) or ""
            data[key] = f"<set:{len(value)} chars>" if value else "<unset>"
        return data
