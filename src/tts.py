"""
Text-to-speech, returning audio already in Twilio's wire format.

ElevenLabs is the default because it will emit `ulaw_8000` directly. That
removes a decode-resample-encode round trip from the middle of the turn
loop, which is worth roughly 150-250 ms per turn on a phone call. On a
two-minute conversation that is the difference between sounding like a
person and sounding like a bad VoIP line.

OpenAI is kept as a fallback for when an ElevenLabs quota runs dry mid-run.
It only speaks linear PCM, so its output goes through the resampler in
`audio.py`. Slower, still usable, no ffmpeg required.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from .audio import pcm16_bytes_to_mulaw
from .config import VoiceConfig

log = logging.getLogger(__name__)

ELEVENLABS_ENDPOINT = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
OPENAI_ENDPOINT = "https://api.openai.com/v1/audio/speech"


class SynthesisError(RuntimeError):
    pass


@dataclass
class Speech:
    mulaw: bytes
    provider: str
    characters: int
    latency_seconds: float


class Synthesiser:
    def __init__(self, voice: VoiceConfig, elevenlabs_key: str = "", openai_key: str = "") -> None:
        self._voice = voice
        self._elevenlabs_key = elevenlabs_key
        self._openai_key = openai_key
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))

    async def speak(self, text: str) -> Speech:
        import time

        started = time.monotonic()
        if self._voice.provider == "elevenlabs":
            mulaw = await self._elevenlabs(text)
            provider = "elevenlabs"
        else:
            mulaw = await self._openai(text)
            provider = "openai"
        return Speech(
            mulaw=mulaw,
            provider=provider,
            characters=len(text),
            latency_seconds=time.monotonic() - started,
        )

    async def _elevenlabs(self, text: str) -> bytes:
        if not self._elevenlabs_key:
            raise SynthesisError("ElevenLabs API key not configured")

        response = await self._client.post(
            ELEVENLABS_ENDPOINT.format(voice_id=self._voice.elevenlabs_voice_id),
            params={"output_format": "ulaw_8000", "optimize_streaming_latency": "3"},
            headers={"xi-api-key": self._elevenlabs_key, "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": self._voice.elevenlabs_model,
                "voice_settings": {
                    # Moderate stability keeps some prosodic variation. Pushed
                    # higher the voice flattens out and stops sounding like a
                    # person with a problem, which is the whole point here.
                    "stability": 0.45,
                    "similarity_boost": 0.75,
                    "style": 0.25,
                    "use_speaker_boost": True,
                },
            },
        )
        if response.status_code >= 400:
            raise SynthesisError(f"ElevenLabs returned {response.status_code}: {response.text[:200]}")
        return response.content

    async def _openai(self, text: str) -> bytes:
        if not self._openai_key:
            raise SynthesisError("OpenAI API key not configured")

        response = await self._client.post(
            OPENAI_ENDPOINT,
            headers={"Authorization": f"Bearer {self._openai_key}"},
            json={
                "model": self._voice.openai_model,
                "voice": self._voice.openai_voice,
                "input": text,
                "response_format": "pcm",  # 24 kHz signed 16-bit little-endian mono
            },
        )
        if response.status_code >= 400:
            raise SynthesisError(f"OpenAI returned {response.status_code}: {response.text[:200]}")
        return pcm16_bytes_to_mulaw(response.content, source_rate=24000)

    async def verify(self) -> tuple[bool, str]:
        """Cheap smoke test used by the dashboard's credential check."""
        try:
            speech = await self.speak("Testing one two three.")
        except SynthesisError as exc:
            return False, str(exc)
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"
        if len(speech.mulaw) < 800:  # under 100 ms of audio means something is wrong
            return False, f"Synthesis returned only {len(speech.mulaw)} bytes"
        return True, f"{speech.provider}, {len(speech.mulaw) / 8000:.2f}s of audio in {speech.latency_seconds:.2f}s"

    async def close(self) -> None:
        await self._client.aclose()
