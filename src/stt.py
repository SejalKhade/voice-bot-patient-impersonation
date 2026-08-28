"""
Live speech-to-text over Deepgram's streaming API.

Written against the raw websocket rather than the vendor SDK. The SDK's
callback surface changed shape between v2, v3 and v4, and a harness that
breaks on `pip install --upgrade` is worse than forty lines of protocol
handling. The wire format has been stable throughout.

Only the inbound Twilio track is fed here, so every transcript this
produces is the far-end agent speaking.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable
from urllib.parse import urlencode

import websockets

from .config import SpeechConfig

log = logging.getLogger(__name__)

DEEPGRAM_URL = "wss://api.deepgram.com/v1/listen"


@dataclass
class Utterance:
    text: str
    confidence: float
    is_final: bool
    speech_final: bool


class DeepgramStream:
    """
    Wraps one Deepgram socket for the lifetime of one call.

    Three callbacks, three distinct meanings:

      on_speech_started  the far end began talking. Fires fast and is the
                         only signal early enough to drive barge-in.
      on_interim         a partial hypothesis. Useful for latency
                         instrumentation, never used as evidence.
      on_utterance       a settled utterance. This is what becomes a turn.
    """

    def __init__(
        self,
        api_key: str,
        speech: SpeechConfig,
        on_utterance: Callable[[Utterance], Awaitable[None]],
        on_speech_started: Callable[[], Awaitable[None]] | None = None,
        on_interim: Callable[[Utterance], Awaitable[None]] | None = None,
    ) -> None:
        self._api_key = api_key
        self._speech = speech
        self._on_utterance = on_utterance
        self._on_speech_started = on_speech_started
        self._on_interim = on_interim

        self._socket: websockets.WebSocketClientProtocol | None = None
        self._reader: asyncio.Task | None = None
        self._closed = asyncio.Event()
        # Deepgram sometimes settles an utterance across several is_final
        # messages before speech_final. Accumulate until then, otherwise a
        # single sentence arrives as three fragmented turns.
        self._pending: list[str] = []
        self._pending_confidence: list[float] = []

    def _url(self) -> str:
        params = {
            "encoding": "mulaw",
            "sample_rate": "8000",
            "channels": "1",
            "model": self._speech.model,
            "interim_results": "true" if self._speech.interim_results else "false",
            "endpointing": str(self._speech.endpointing_ms),
            "utterance_end_ms": str(self._speech.utterance_end_ms),
            "vad_events": "true",
            "smart_format": "true",
            "punctuate": "true",
            "filler_words": "false",
        }
        return f"{DEEPGRAM_URL}?{urlencode(params)}"

    async def connect(self) -> None:
        self._socket = await websockets.connect(
            self._url(),
            additional_headers={"Authorization": f"Token {self._api_key}"},
            ping_interval=5,
            ping_timeout=20,
            max_size=None,
        )
        self._reader = asyncio.create_task(self._read_loop())
        log.info("Deepgram stream open (model=%s)", self._speech.model)

    async def send_audio(self, mulaw: bytes) -> None:
        if self._socket is None or self._closed.is_set():
            return
        try:
            await self._socket.send(mulaw)
        except websockets.ConnectionClosed:
            self._closed.set()

    async def _read_loop(self) -> None:
        assert self._socket is not None
        try:
            async for raw in self._socket:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await self._dispatch(message)
        except websockets.ConnectionClosed:
            pass
        except Exception:  # noqa: BLE001 - a dead STT socket must not kill the call
            log.exception("Deepgram read loop failed")
        finally:
            self._closed.set()

    async def _dispatch(self, message: dict) -> None:
        kind = message.get("type")

        if kind == "SpeechStarted":
            if self._on_speech_started:
                await self._on_speech_started()
            return

        if kind == "UtteranceEnd":
            await self._flush()
            return

        if kind != "Results":
            return

        alternatives = message.get("channel", {}).get("alternatives", [])
        if not alternatives:
            return

        text = (alternatives[0].get("transcript") or "").strip()
        confidence = float(alternatives[0].get("confidence") or 0.0)
        is_final = bool(message.get("is_final"))
        speech_final = bool(message.get("speech_final"))

        if not text:
            if speech_final:
                await self._flush()
            return

        if not is_final:
            if self._on_interim:
                await self._on_interim(Utterance(text, confidence, False, False))
            return

        self._pending.append(text)
        self._pending_confidence.append(confidence)

        if speech_final:
            await self._flush()

    async def _flush(self) -> None:
        if not self._pending:
            return
        text = " ".join(self._pending).strip()
        confidence = sum(self._pending_confidence) / len(self._pending_confidence)
        self._pending.clear()
        self._pending_confidence.clear()
        if text:
            await self._on_utterance(Utterance(text, confidence, True, True))

    async def close(self) -> None:
        if self._socket is None:
            return
        try:
            await self._socket.send(json.dumps({"type": "CloseStream"}))
            await asyncio.wait_for(self._closed.wait(), timeout=3)
        except (websockets.ConnectionClosed, asyncio.TimeoutError):
            pass
        finally:
            if self._reader:
                self._reader.cancel()
            try:
                await self._socket.close()
            except Exception:  # noqa: BLE001
                pass
            log.info("Deepgram stream closed")
