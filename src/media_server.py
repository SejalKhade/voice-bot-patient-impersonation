"""
The media bridge. This is where a call actually happens.

Runs as its own uvicorn process rather than inside Streamlit. Streamlit
re-executes its script top to bottom on every widget interaction, which is
fatal to a long-lived websocket holding a phone call open. Splitting them
means the call survives anything the user clicks.

Audio path per call:

    Twilio  --websocket-->  this process  --websocket-->  Deepgram
                                 |
                                 v
                          patient brain (Claude)
                                 |
                                 v
    Twilio  <--websocket--  this process  <--https--  ElevenLabs

Why not a realtime speech-to-speech API? Three reasons, in order of weight.
First, the transcript is the deliverable: bugs have to be cited to exact
turn indices with verbatim quotes, and a cascade gives a clean, timestamped,
speaker-attributed record for free. Second, control: barge-in thresholds,
endpointing and turn policy are all things this assessment explicitly asks
me to stress, and a realtime API hides them behind vendor defaults. Third,
attribution: when a call sounds wrong I need to know whether it was STT,
the brain or TTS, and a single opaque model makes that undiagnosable. The
cost is latency, roughly 300-500 ms more per turn than speech-to-speech.
That is a real trade, made deliberately.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

from . import audio
from .config import RunConfig
from .patient import PatientBrain
from .scenarios import Scenario, by_id
from .stt import DeepgramStream, Utterance
from .transcript import AGENT, PATIENT, Transcript
from .tts import Synthesiser, SynthesisError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
log = logging.getLogger("media_server")

app = FastAPI(title="Voice QA Media Bridge")

RECORDINGS_DIR = Path("data/recordings")


@dataclass
class Session:
    """Everything one call needs, held in memory for its lifetime."""

    session_id: str
    scenario: Scenario
    config: RunConfig
    transcript: Transcript
    run_id: str = ""             # namespaces the recording so re-running the
                                  # same scenario in a later run can't clobber
                                  # an earlier one's saved audio
    call_sid: str | None = None
    stream_sid: str | None = None
    status: str = "created"
    log_lines: list[str] = field(default_factory=list)

    # Turn-loop state
    speaking: bool = False
    agent_last_ended: float | None = None
    last_inbound_at: float = field(default_factory=time.monotonic)
    started_monotonic: float = field(default_factory=time.monotonic)
    generation: int = 0          # bumped on barge-in to abandon stale playback
    turns_taken: int = 0
    error: str | None = None
    agent_has_spoken: bool = False  # set the instant Deepgram sees agent speech

    def note(self, message: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        line = f"{stamp}  {message}"
        self.log_lines.append(line)
        log.info("[%s] %s", self.session_id[:8], message)


SESSIONS: dict[str, Session] = {}


# ---------------------------------------------------------------------------
# Control plane
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "sessions": len(SESSIONS)}


@app.post("/calls")
async def create_call(request: Request) -> JSONResponse:
    """Place one outbound call. Returns immediately; poll /calls/{id} for state."""
    body = await request.json()
    config = _config_from_payload(body["config"])
    scenario = by_id(body["scenario_id"])
    call_id = body.get("call_id") or f"call_{scenario.id}"
    run_id = body.get("run_id") or ""

    session_id = uuid.uuid4().hex
    session = Session(
        session_id=session_id,
        scenario=scenario,
        config=config,
        run_id=run_id,
        transcript=Transcript(
            call_id=call_id,
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            from_number=config.twilio_from_number,
            to_number=config.target_number,
        ),
    )
    SESSIONS[session_id] = session
    session.note(f"Session created for {scenario.id}: {scenario.title}")

    try:
        from twilio.rest import Client

        client = Client(config.twilio_account_sid, config.twilio_auth_token)
        call = client.calls.create(
            to=config.target_number,
            from_=config.twilio_from_number,
            url=f"https://{config.public_base_url}/twiml/{session_id}",
            method="POST",
            record=True,
            recording_channels="dual",
            time_limit=config.policy.max_call_seconds,
            status_callback=f"https://{config.public_base_url}/status/{session_id}",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST",
        )
        session.call_sid = call.sid
        session.transcript.call_sid = call.sid
        session.status = "dialing"
        session.note(f"Dialing {config.target_number} (SID {call.sid})")
    except Exception as exc:  # noqa: BLE001
        session.status = "failed"
        session.error = f"{type(exc).__name__}: {exc}"
        session.note(f"Dial failed: {session.error}")
        return JSONResponse({"session_id": session_id, "error": session.error}, status_code=502)

    return JSONResponse({"session_id": session_id, "call_sid": session.call_sid, "status": session.status})


@app.get("/calls/{session_id}")
async def get_call(session_id: str) -> JSONResponse:
    session = SESSIONS.get(session_id)
    if session is None:
        return JSONResponse({"error": "unknown session"}, status_code=404)
    return JSONResponse(
        {
            "session_id": session_id,
            "status": session.status,
            "call_sid": session.call_sid,
            "error": session.error,
            "turns": len(session.transcript.turns),
            "log": session.log_lines,
            "transcript": session.transcript.to_dict(),
        }
    )


@app.post("/status/{session_id}")
async def call_status(session_id: str, request: Request) -> Response:
    """Twilio call-progress webhook. Authoritative for terminal states."""
    form = await request.form()
    session = SESSIONS.get(session_id)
    if session:
        state = form.get("CallStatus", "")
        session.note(f"Twilio status: {state}")
        if state in {"completed", "failed", "busy", "no-answer", "canceled"}:
            if session.status not in {"finished", "failed"}:
                session.status = "finished" if state == "completed" else "failed"
                session.transcript.termination_reason = session.transcript.termination_reason or f"twilio:{state}"
    return Response(status_code=204)


@app.post("/twiml/{session_id}")
async def twiml(session_id: str) -> Response:
    """
    Answer webhook. `<Connect><Stream>` gives a bidirectional socket, which
    is what makes the bot able to speak rather than only listen.
    """
    session = SESSIONS.get(session_id)
    if session is None:
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>',
            media_type="application/xml",
        )
    host = session.config.public_base_url
    session.note("Call answered, opening media stream")
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Connect><Stream url="wss://{host}/stream/{session_id}" /></Connect>'
        "</Response>"
    )
    return Response(content=document, media_type="application/xml")


# ---------------------------------------------------------------------------
# Media plane
# ---------------------------------------------------------------------------


@app.websocket("/stream/{session_id}")
async def stream(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    session = SESSIONS.get(session_id)
    if session is None:
        await websocket.close()
        return

    session.status = "connected"
    session.started_monotonic = time.monotonic()
    brain = PatientBrain(session.scenario, session.config.anthropic_api_key, session.config.models)
    synth = Synthesiser(session.config.voice, session.config.elevenlabs_api_key, session.config.openai_api_key)

    # --- outbound audio -----------------------------------------------------

    async def send_speech(text: str, latency: float | None = None) -> None:
        """
        Push one utterance to the caller side of the line.

        Frames are paced in real time. Twilio will accept a whole buffer at
        once, but then the bot cannot be interrupted mid-sentence because
        the audio is already queued in Twilio's jitter buffer. Pacing keeps
        barge-in responsive at the cost of holding the coroutine open.
        """
        if not text.strip():
            return

        my_generation = session.generation
        try:
            speech = await synth.speak(text)
        except SynthesisError as exc:
            session.note(f"Synthesis failed: {exc}")
            session.transcript.add_event("tts_error", str(exc))
            return

        turn = session.transcript.add_turn(PATIENT, text, response_latency=latency)
        session.turns_taken += 1
        session.note(f"PATIENT [{turn.index:03d}]: {text}")

        session.speaking = True
        frame_period = audio.FRAME_MS / 1000.0
        next_send = time.monotonic()

        for frame in audio.frames(speech.mulaw):
            if session.generation != my_generation:
                turn.interrupted = True
                session.note("Playback abandoned: caller barged in")
                break
            try:
                await websocket.send_text(
                    json.dumps(
                        {
                            "event": "media",
                            "streamSid": session.stream_sid,
                            "media": {"payload": audio.encode_frame(frame)},
                        }
                    )
                )
            except (WebSocketDisconnect, RuntimeError):
                break
            next_send += frame_period
            drift = next_send - time.monotonic()
            if drift > 0:
                await asyncio.sleep(drift)
            else:
                next_send = time.monotonic()

        session.speaking = False

    async def clear_playback() -> None:
        """Flush Twilio's buffer so an interrupted sentence stops immediately."""
        session.generation += 1
        try:
            await websocket.send_text(json.dumps({"event": "clear", "streamSid": session.stream_sid}))
        except (WebSocketDisconnect, RuntimeError):
            pass

    # --- inbound speech handling -------------------------------------------

    turn_lock = asyncio.Lock()

    async def on_speech_started() -> None:
        """
        Barge-in.

        Only fires while the bot is mid-sentence. Scenarios that are not
        testing interruption still need this: without it the bot talks over
        the agent's clarifying questions and the call degenerates into two
        monologues.
        """
        session.agent_has_spoken = True
        if session.speaking and session.config.policy.barge_in_enabled:
            session.transcript.add_event("barge_in", "Agent began speaking during caller playback")
            await clear_playback()

    async def on_utterance(utterance: Utterance) -> None:
        session.last_inbound_at = time.monotonic()
        text = utterance.text.strip()
        if len(text) < 2:
            return

        turn = session.transcript.add_turn(AGENT, text, confidence=utterance.confidence)
        session.note(f"AGENT   [{turn.index:03d}]: {text}")
        session.agent_last_ended = time.monotonic()

        if turn_lock.locked():
            # The agent kept talking while we were already composing a reply.
            # Drop this trigger; the next reply will have seen both turns.
            return

        async with turn_lock:
            if _should_stop(session, brain):
                await _wind_down(session, brain, send_speech)
                return
            reply = await brain.reply_to(text)
            latency = time.monotonic() - (session.agent_last_ended or time.monotonic())
            await send_speech(reply, latency=latency)
            if brain.state.wants_to_end:
                session.transcript.termination_reason = "caller:objective-resolved"
                await asyncio.sleep(1.5)
                await _hangup(session)

    deepgram = DeepgramStream(
        api_key=session.config.deepgram_api_key,
        speech=session.config.speech,
        on_utterance=on_utterance,
        on_speech_started=on_speech_started,
    )

    watchdog: asyncio.Task | None = None

    try:
        await deepgram.connect()
        watchdog = asyncio.create_task(_watchdog(session))

        async for raw in websocket.iter_text():
            message = json.loads(raw)
            event = message.get("event")

            if event == "start":
                session.stream_sid = message["start"]["streamSid"]
                session.note("Media stream started")
                asyncio.create_task(_open_conversation(session, brain, send_speech))

            elif event == "media":
                if message.get("media", {}).get("track") == "outbound":
                    continue  # our own audio looped back; do not transcribe it
                chunk = audio.decode_payload(message["media"]["payload"])
                session.last_inbound_at = time.monotonic()
                await deepgram.send_audio(chunk)

            elif event == "stop":
                session.note("Media stream stopped by Twilio")
                break

    except WebSocketDisconnect:
        session.note("Websocket disconnected")
    except Exception as exc:  # noqa: BLE001
        session.error = f"{type(exc).__name__}: {exc}"
        session.note(f"Stream error: {session.error}")
        log.exception("Stream failure")
    finally:
        if watchdog:
            watchdog.cancel()
        await deepgram.close()
        await brain.update_probe_coverage()
        session.transcript.ended_at = datetime.now(timezone.utc).isoformat()
        session.transcript.termination_reason = session.transcript.termination_reason or "stream:closed"
        session.transcript.add_event(
            "probe_coverage",
            f"{brain.probe_coverage():.0%} of scenario probes raised "
            f"({len(set(brain.state.probes_landed))}/{len(session.scenario.probes)})",
        )
        await brain.close()
        await synth.close()
        session.status = "finished" if session.error is None else "failed"
        session.note(f"Call finished with {len(session.transcript.turns)} turns")
        asyncio.create_task(_fetch_recording(session))


async def _open_conversation(session: Session, brain: PatientBrain, send_speech) -> None:
    """
    Speak first, but not immediately.

    A real caller lets the other end say hello. Jumping in at zero
    milliseconds clips the agent's greeting, which both sounds wrong and
    corrupts the first agent turn in the transcript.

    The delay alone isn't enough: it fires unconditionally once elapsed,
    with no regard for whether the agent's own greeting happened to start
    during that same window (call_01_S02 in run_20260903_070441 showed a
    patient turn and an agent turn starting 61ms apart). Re-checked right
    before speaking, and once more after synthesis - synthesis itself can
    take a second or more, which is long enough for the agent to start in
    the meantime.
    """
    await asyncio.sleep(session.config.policy.opening_delay_seconds)
    if session.agent_has_spoken:
        return
    opening = await brain.opening_line()
    if session.agent_has_spoken:
        return
    await send_speech(opening)


def _should_stop(session: Session, brain: PatientBrain) -> bool:
    if session.turns_taken >= session.config.policy.max_turns:
        session.transcript.termination_reason = "policy:max-turns"
        return True
    if time.monotonic() - session.started_monotonic >= session.config.policy.max_call_seconds - 15:
        session.transcript.termination_reason = "policy:max-duration"
        return True
    return False


async def _wind_down(session: Session, brain: PatientBrain, send_speech) -> None:
    session.note("Policy limit reached, closing politely")
    await send_speech("Alright, that's everything I needed. Thanks very much for your help. Goodbye.")
    await asyncio.sleep(1.5)
    await _hangup(session)


async def _watchdog(session: Session) -> None:
    """Hang up on dead air or a runaway call so credit is not burned silently."""
    policy = session.config.policy
    while True:
        await asyncio.sleep(2)
        idle = time.monotonic() - session.last_inbound_at
        elapsed = time.monotonic() - session.started_monotonic
        if idle > policy.silence_timeout_seconds:
            session.transcript.termination_reason = "watchdog:silence"
            session.transcript.add_event("watchdog", f"No inbound audio for {idle:.0f}s")
            session.note(f"Watchdog: {idle:.0f}s of silence, hanging up")
            await _hangup(session)
            return
        if elapsed > policy.max_call_seconds:
            session.transcript.termination_reason = "watchdog:duration"
            session.note("Watchdog: maximum call duration reached")
            await _hangup(session)
            return


async def _hangup(session: Session) -> None:
    if not session.call_sid:
        return
    try:
        from twilio.rest import Client

        client = Client(session.config.twilio_account_sid, session.config.twilio_auth_token)
        client.calls(session.call_sid).update(status="completed")
        session.note("Hangup requested")
    except Exception as exc:  # noqa: BLE001
        session.note(f"Hangup failed: {exc}")


async def _fetch_recording(session: Session) -> None:
    """
    Pull the dual-channel recording once Twilio has finished encoding it.

    Twilio does not expose the asset the instant the call ends, so this
    polls rather than assuming. MP3 because the assessment asks for MP3 or
    OGG and MP3 needs no re-encode.
    """
    if not session.call_sid:
        return
    # Namespaced by run_id so re-running the same scenario id in a later,
    # separate invocation can't silently overwrite an earlier run's audio -
    # call_id alone (e.g. "call_01_S01") repeats across runs.
    recordings_dir = RECORDINGS_DIR / session.run_id if session.run_id else RECORDINGS_DIR
    recordings_dir.mkdir(parents=True, exist_ok=True)
    auth = (session.config.twilio_account_sid, session.config.twilio_auth_token)

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(12):
            await asyncio.sleep(5)
            try:
                listing = await client.get(
                    f"https://api.twilio.com/2010-04-01/Accounts/{session.config.twilio_account_sid}"
                    f"/Recordings.json?CallSid={session.call_sid}",
                    auth=auth,
                )
                recordings = listing.json().get("recordings", [])
                if not recordings:
                    continue
                sid = recordings[0]["sid"]
                media = await client.get(
                    f"https://api.twilio.com/2010-04-01/Accounts/"
                    f"{session.config.twilio_account_sid}/Recordings/{sid}.mp3",
                    auth=auth,
                    follow_redirects=True,
                )
                if media.status_code != 200 or len(media.content) < 1024:
                    continue
                destination = recordings_dir / f"{session.transcript.call_id}.mp3"
                destination.write_bytes(media.content)
                session.transcript.recording_path = str(destination)
                session.note(f"Recording saved: {destination} ({len(media.content) // 1024} KB)")
                return
            except Exception as exc:  # noqa: BLE001
                session.note(f"Recording fetch attempt {attempt + 1} failed: {exc}")
    session.note("Recording unavailable after 12 attempts")


def _config_from_payload(payload: dict) -> RunConfig:
    from .config import CallPolicy, ModelConfig, SpeechConfig, VoiceConfig

    nested = {
        "models": ModelConfig(**payload.pop("models", {})),
        "voice": VoiceConfig(**payload.pop("voice", {})),
        "speech": SpeechConfig(**payload.pop("speech", {})),
        "policy": CallPolicy(**payload.pop("policy", {})),
    }
    known = {f for f in RunConfig.__dataclass_fields__ if f not in nested}
    flat = {k: v for k, v in payload.items() if k in known}
    return RunConfig(**flat, **nested)
