"""
Voice QA Console.

A control surface for the harness. Its one job is to make every number on
screen traceable to the thing that produced it: a gate that passed, a quote
that matched, a multiplication that was performed. Nothing is presented as
a verdict without its derivation attached.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
import streamlit as st

from src import ground_truth as gt
from src.analyzer import DIMENSIONS, Finding
from src.config import CallPolicy, ModelConfig, RunConfig, SpeechConfig, VoiceConfig
from src.orchestrator import MediaServer, Pipeline
from src.scenarios import SCENARIOS, by_id
from src.scoring import (
    BASE_SCORE,
    DIMENSION_LABELS,
    DIMENSION_WEIGHTS,
    SEVERITY_WEIGHTS,
    score_run,
)
from src.store import RunStore, build_bug_report
from src.transcript import Transcript
from src.tts import Synthesiser
from src.verifier import (
    CONFIDENCE_THRESHOLD,
    STATUS_QUARANTINED,
    STATUS_REJECTED,
    STATUS_UNVERIFIED,
    STATUS_VERIFIED,
)

st.set_page_config(
    page_title="Voice QA Console",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Progress from the worker thread lands here. Module-level rather than in
# session_state because Streamlit's session context does not follow a thread.
RUN_BUS: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
  --paper:    #FBFBFC;
  --panel:    #FFFFFF;
  --ink:      #14181D;
  --muted:    #5C6672;
  --faint:    #8A94A0;
  --rule:     #DCE0E6;
  --signal:   #1D4E7C;
  --verified: #1A6B4A;
  --withheld: #8A6A22;
  --rejected: #8C3A3A;
  --critical: #7A2230;
}

html, body, [class*="css"], .stApp { background: var(--paper); }
.stApp, .stMarkdown, p, li, label, span, div { font-family: 'IBM Plex Sans', system-ui, sans-serif; color: var(--ink); }
h1, h2, h3, h4 { font-family: 'IBM Plex Sans', sans-serif; font-weight: 600; letter-spacing: -0.015em; color: var(--ink); }
code, pre, .mono { font-family: 'IBM Plex Mono', ui-monospace, monospace; }

#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2.2rem; max-width: 1500px; }

.masthead { border-bottom: 2px solid var(--ink); padding-bottom: 0.9rem; margin-bottom: 1.6rem; }
.masthead .title { font-size: 1.55rem; font-weight: 700; letter-spacing: -0.02em; }
.masthead .sub { font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem;
  text-transform: uppercase; letter-spacing: 0.14em; color: var(--muted); margin-top: 0.3rem; }

.eyebrow { font-family: 'IBM Plex Mono', monospace; font-size: 0.68rem; text-transform: uppercase;
  letter-spacing: 0.16em; color: var(--faint); margin: 1.6rem 0 0.5rem; }

.panel { background: var(--panel); border: 1px solid var(--rule); padding: 1.1rem 1.25rem; margin-bottom: 0.9rem; }
.panel.flag-verified   { border-left: 3px solid var(--verified); }
.panel.flag-unverified { border-left: 3px solid var(--withheld); }
.panel.flag-quarantined{ border-left: 3px solid var(--withheld); }
.panel.flag-rejected   { border-left: 3px solid var(--rejected); }

.stat-row { display: flex; gap: 0; border: 1px solid var(--rule); background: var(--panel); margin-bottom: 1.2rem; }
.stat { flex: 1; padding: 0.9rem 1.1rem; border-right: 1px solid var(--rule); }
.stat:last-child { border-right: none; }
.stat .k { font-family: 'IBM Plex Mono', monospace; font-size: 0.64rem; text-transform: uppercase;
  letter-spacing: 0.13em; color: var(--faint); }
.stat .v { font-family: 'IBM Plex Mono', monospace; font-size: 1.5rem; font-weight: 600;
  color: var(--ink); line-height: 1.35; }
.stat .n { font-size: 0.72rem; color: var(--muted); }

.tag { display: inline-block; font-family: 'IBM Plex Mono', monospace; font-size: 0.62rem;
  text-transform: uppercase; letter-spacing: 0.1em; padding: 0.16rem 0.5rem;
  border: 1px solid var(--rule); color: var(--muted); margin-right: 0.35rem; }
.tag.verified   { border-color: var(--verified); color: var(--verified); }
.tag.unverified { border-color: var(--withheld); color: var(--withheld); }
.tag.quarantined{ border-color: var(--withheld); color: var(--withheld); }
.tag.rejected   { border-color: var(--rejected); color: var(--rejected); }
.tag.critical   { border-color: var(--critical); color: var(--critical); background: #FBF4F5; }
.tag.high       { border-color: var(--rejected); color: var(--rejected); }
.tag.medium     { border-color: var(--withheld); color: var(--withheld); }
.tag.low        { border-color: var(--rule); color: var(--muted); }

/* Gate strip: the verification chain, rendered as a sequence because it is one. */
.gates { display: flex; gap: 0; margin: 0.7rem 0 0.4rem; border: 1px solid var(--rule); }
.gate { flex: 1; padding: 0.6rem 0.75rem; border-right: 1px solid var(--rule); background: var(--panel); }
.gate:last-child { border-right: none; }
.gate .num { font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; letter-spacing: 0.12em;
  color: var(--faint); text-transform: uppercase; }
.gate .nm { font-size: 0.78rem; font-weight: 600; margin: 0.1rem 0 0.25rem; }
.gate .st { font-family: 'IBM Plex Mono', monospace; font-size: 0.68rem; font-weight: 600; letter-spacing: 0.06em; }
.gate.pass .st { color: var(--verified); }
.gate.fail .st { color: var(--rejected); }
.gate.skip .st { color: var(--faint); }
.gate .dt { font-size: 0.7rem; color: var(--muted); line-height: 1.45; margin-top: 0.3rem; }

.calc { font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; border: 1px solid var(--rule);
  background: var(--panel); }
.calc .ln { display: flex; justify-content: space-between; padding: 0.42rem 0.8rem;
  border-bottom: 1px solid var(--rule); }
.calc .ln:last-child { border-bottom: none; }
.calc .ln.total { border-top: 2px solid var(--ink); font-weight: 600; background: #F5F7F9; }
.calc .lbl { color: var(--muted); }
.calc .exp { color: var(--ink); text-align: right; }

.quote { border-left: 3px solid var(--signal); background: #F6F8FA; padding: 0.7rem 1rem;
  font-family: 'IBM Plex Mono', monospace; font-size: 0.82rem; line-height: 1.65; margin: 0.6rem 0; }

.turn { display: grid; grid-template-columns: 62px 78px 1fr; gap: 0.8rem; padding: 0.5rem 0;
  border-bottom: 1px solid #EEF0F3; font-size: 0.87rem; line-height: 1.6; }
.turn .idx { font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; color: var(--faint); padding-top: 0.15rem; }
.turn .who { font-family: 'IBM Plex Mono', monospace; font-size: 0.66rem; letter-spacing: 0.09em;
  padding-top: 0.2rem; }
.turn.agent   .who { color: var(--signal); }
.turn.patient .who { color: var(--muted); }
.turn.agent   { background: #F8FAFC; }
.turn .meta { font-family: 'IBM Plex Mono', monospace; font-size: 0.66rem; color: var(--faint); }

.note { font-size: 0.8rem; color: var(--muted); line-height: 1.6; }
.warnbox { border: 1px solid var(--withheld); border-left: 3px solid var(--withheld);
  background: #FDFBF4; padding: 0.85rem 1.05rem; font-size: 0.82rem; line-height: 1.6; margin-bottom: 0.9rem; }
.okbox { border: 1px solid var(--verified); border-left: 3px solid var(--verified);
  background: #F4FAF7; padding: 0.85rem 1.05rem; font-size: 0.82rem; line-height: 1.6; margin-bottom: 0.9rem; }

.stButton > button { font-family: 'IBM Plex Sans', sans-serif; font-weight: 500; border-radius: 0;
  border: 1px solid var(--ink); background: var(--ink); color: #fff; letter-spacing: 0.01em; }
.stButton > button:hover { background: var(--signal); border-color: var(--signal); color: #fff; }
.stTextInput input, .stNumberInput input, .stTextArea textarea {
  border-radius: 0 !important; font-family: 'IBM Plex Mono', monospace !important; font-size: 0.82rem !important; }
.stTabs [data-baseweb="tab"] { font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem;
  text-transform: uppercase; letter-spacing: 0.1em; }
section[data-testid="stSidebar"] { background: #F4F6F8; border-right: 1px solid var(--rule); }
section[data-testid="stSidebar"] .stMarkdown p { font-size: 0.82rem; }
hr { border-color: var(--rule); }
</style>
"""

st.markdown(STYLE, unsafe_allow_html=True)


def eyebrow(text: str) -> None:
    st.markdown(f'<div class="eyebrow">{text}</div>', unsafe_allow_html=True)


def stat_row(items: list[tuple[str, str, str]]) -> None:
    cells = "".join(
        f'<div class="stat"><div class="k">{k}</div><div class="v">{v}</div><div class="n">{n}</div></div>'
        for k, v, n in items
    )
    st.markdown(f'<div class="stat-row">{cells}</div>', unsafe_allow_html=True)


def calc_block(lines: list[tuple[str, str]], total: tuple[str, str] | None = None) -> None:
    rows = "".join(
        f'<div class="ln"><span class="lbl">{lbl}</span><span class="exp">{exp}</span></div>'
        for lbl, exp in lines
    )
    if total:
        rows += f'<div class="ln total"><span class="lbl">{total[0]}</span><span class="exp">{total[1]}</span></div>'
    st.markdown(f'<div class="calc">{rows}</div>', unsafe_allow_html=True)


def gate_strip(gates: list[dict]) -> None:
    cells = []
    for gate in gates:
        state = "pass" if gate["passed"] else "fail"
        label = "PASS" if gate["passed"] else "FAIL"
        cells.append(
            f'<div class="gate {state}">'
            f'<div class="num">Gate {gate["number"]}</div>'
            f'<div class="nm">{gate["name"]}</div>'
            f'<div class="st">{label}</div>'
            f'<div class="dt">{gate["detail"]}</div>'
            f"</div>"
        )
    for missing in range(len(gates), 4):
        cells.append(
            f'<div class="gate skip"><div class="num">Gate {missing + 1}</div>'
            f'<div class="nm">Not reached</div><div class="st">SKIPPED</div>'
            f'<div class="dt">The finding stopped at an earlier gate.</div></div>'
        )
    st.markdown(f'<div class="gates">{"".join(cells)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

DEFAULTS = {
    "config": RunConfig.from_env(),
    "checks": {},
    "run_id": None,
    "running": False,
    "selected": [s.id for s in SCENARIOS[:12]],
    "loaded_run": None,
}
for key, value in DEFAULTS.items():
    st.session_state.setdefault(key, value)

config: RunConfig = st.session_state.config


# ---------------------------------------------------------------------------
# Sidebar: credentials
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        '<div class="masthead"><div class="title">Configuration</div>'
        '<div class="sub">Credentials held in memory only</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="note">Keys stay in this browser session. They are sent to the local '
        "media server over loopback and are never written to disk. Run files record only "
        "whether a key was set.</div>",
        unsafe_allow_html=True,
    )

    eyebrow("Telephony — Twilio")
    config.twilio_account_sid = st.text_input("Account SID", value=config.twilio_account_sid, type="password")
    config.twilio_auth_token = st.text_input("Auth token", value=config.twilio_auth_token, type="password")
    config.twilio_from_number = st.text_input(
        "Your Twilio number (E.164)", value=config.twilio_from_number, placeholder="+15551234567"
    )

    eyebrow("Reasoning — Anthropic")
    config.anthropic_api_key = st.text_input("Anthropic API key", value=config.anthropic_api_key, type="password")

    eyebrow("Speech to text — Deepgram")
    config.deepgram_api_key = st.text_input("Deepgram API key", value=config.deepgram_api_key, type="password")

    eyebrow("Text to speech")
    config.voice.provider = st.selectbox(
        "Provider", ["elevenlabs", "openai"],
        index=0 if config.voice.provider == "elevenlabs" else 1,
    )
    if config.voice.provider == "elevenlabs":
        config.elevenlabs_api_key = st.text_input("ElevenLabs API key", value=config.elevenlabs_api_key, type="password")
        config.voice.elevenlabs_voice_id = st.text_input("Voice ID", value=config.voice.elevenlabs_voice_id)
    else:
        config.openai_api_key = st.text_input("OpenAI API key", value=config.openai_api_key, type="password")
        config.voice.openai_voice = st.selectbox(
            "Voice", ["alloy", "echo", "fable", "onyx", "nova", "shimmer"], index=0
        )

    eyebrow("Public tunnel")
    config.public_base_url = st.text_input(
        "ngrok host (no scheme)", value=config.public_base_url, placeholder="a1b2c3d4.ngrok-free.app"
    ).replace("https://", "").replace("http://", "").rstrip("/")

    eyebrow("Target")
    config.target_number = st.text_input("Number under test", value=config.target_number)
    st.markdown(
        '<div class="note">Do not change this unless you are testing your own line.</div>',
        unsafe_allow_html=True,
    )

    with st.expander("Models and call policy"):
        config.models.patient = st.text_input("Caller model (latency-critical)", value=config.models.patient)
        config.models.analyst = st.text_input("Analyst model", value=config.models.analyst)
        config.models.adjudicator = st.text_input("Adjudicator model", value=config.models.adjudicator)
        config.models.adjudicator_samples = st.slider(
            "Adjudicator samples per finding", 1, 5, config.models.adjudicator_samples,
            help="More samples give a more stable agreement rate at higher cost.",
        )
        config.policy.max_call_seconds = st.slider("Max call length (s)", 60, 360, config.policy.max_call_seconds)
        config.policy.max_turns = st.slider("Max caller turns", 6, 40, config.policy.max_turns)
        config.policy.inter_call_cooldown_seconds = st.slider(
            "Cooldown between calls (s)", 0, 120, config.policy.inter_call_cooldown_seconds
        )
        config.speech.endpointing_ms = st.slider(
            "Endpointing (ms)", 100, 800, config.speech.endpointing_ms,
            help="Lower reacts faster but cuts in on mid-sentence pauses.",
        )
        config.policy.barge_in_enabled = st.checkbox("Enable barge-in", value=config.policy.barge_in_enabled)

st.session_state.config = config


# ---------------------------------------------------------------------------
# Masthead
# ---------------------------------------------------------------------------

st.markdown(
    '<div class="masthead">'
    '<div class="title">Voice QA Console</div>'
    '<div class="sub">Automated caller simulation, evidence-gated defect analysis, transparent scoring</div>'
    "</div>",
    unsafe_allow_html=True,
)

tabs = st.tabs(
    ["Preflight", "Scenarios", "Run", "Transcripts", "Findings", "Scoring", "Method", "Export"]
)


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

with tabs[0]:
    eyebrow("Requirements")
    problems = config.missing_requirements()
    if problems:
        st.markdown(
            '<div class="warnbox"><strong>Configuration incomplete.</strong><br>'
            + "<br>".join(f"— {p}" for p in problems)
            + "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="okbox"><strong>All required fields are present.</strong> '
            "Run the credential checks below before placing calls.</div>",
            unsafe_allow_html=True,
        )

    eyebrow("Live credential checks")
    st.markdown(
        '<div class="note">Each check makes one real, minimal request. A field being '
        "non-empty is not evidence that it works.</div>",
        unsafe_allow_html=True,
    )

    if st.button("Run credential checks", key="verify"):
        results: dict[str, tuple[bool, str]] = {}

        # Twilio
        try:
            response = httpx.get(
                f"https://api.twilio.com/2010-04-01/Accounts/{config.twilio_account_sid}.json",
                auth=(config.twilio_account_sid, config.twilio_auth_token), timeout=15.0,
            )
            if response.status_code == 200:
                account = response.json()
                results["Twilio"] = (True, f"{account.get('friendly_name', 'account')} — {account.get('status')}")
            else:
                results["Twilio"] = (False, f"HTTP {response.status_code}: {response.text[:160]}")
        except Exception as exc:  # noqa: BLE001
            results["Twilio"] = (False, str(exc))

        # Twilio number ownership
        try:
            response = httpx.get(
                f"https://api.twilio.com/2010-04-01/Accounts/{config.twilio_account_sid}/IncomingPhoneNumbers.json",
                auth=(config.twilio_account_sid, config.twilio_auth_token), timeout=15.0,
            )
            owned = [n["phone_number"] for n in response.json().get("incoming_phone_numbers", [])]
            if config.twilio_from_number in owned:
                results["Twilio number"] = (True, f"{config.twilio_from_number} is on this account")
            else:
                results["Twilio number"] = (
                    False,
                    f"{config.twilio_from_number} not found. On this account: {', '.join(owned) or 'none'}",
                )
        except Exception as exc:  # noqa: BLE001
            results["Twilio number"] = (False, str(exc))

        # Anthropic
        try:
            response = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": config.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={"model": config.models.patient, "max_tokens": 8,
                      "messages": [{"role": "user", "content": "Reply with the word ok."}]},
                timeout=30.0,
            )
            if response.status_code == 200:
                results["Anthropic"] = (True, f"{config.models.patient} responded")
            else:
                results["Anthropic"] = (False, f"HTTP {response.status_code}: {response.text[:200]}")
        except Exception as exc:  # noqa: BLE001
            results["Anthropic"] = (False, str(exc))

        # Deepgram
        try:
            response = httpx.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {config.deepgram_api_key}"}, timeout=15.0,
            )
            if response.status_code == 200:
                projects = response.json().get("projects", [])
                results["Deepgram"] = (True, f"{len(projects)} project(s) visible")
            else:
                results["Deepgram"] = (False, f"HTTP {response.status_code}: {response.text[:160]}")
        except Exception as exc:  # noqa: BLE001
            results["Deepgram"] = (False, str(exc))

        # TTS
        try:
            synth = Synthesiser(config.voice, config.elevenlabs_api_key, config.openai_api_key)
            ok, detail = asyncio.run(synth.verify())
            asyncio.run(synth.close())
            results["Text to speech"] = (ok, detail)
        except Exception as exc:  # noqa: BLE001
            results["Text to speech"] = (False, str(exc))

        # Tunnel
        if config.public_base_url:
            try:
                response = httpx.get(f"https://{config.public_base_url}/health", timeout=12.0)
                if response.status_code == 200:
                    results["Public tunnel"] = (True, "ngrok reaches the local media server")
                else:
                    results["Public tunnel"] = (
                        False, f"Reachable but returned HTTP {response.status_code}. Is the media server running?"
                    )
            except Exception as exc:  # noqa: BLE001
                results["Public tunnel"] = (
                    False, f"Not reachable: {exc}. Start the media server, then ngrok."
                )
        st.session_state.checks = results

    if st.session_state.checks:
        for name, (ok, detail) in st.session_state.checks.items():
            css = "okbox" if ok else "warnbox"
            label = "PASS" if ok else "FAIL"
            st.markdown(
                f'<div class="{css}"><span class="mono"><strong>{label}</strong></span> &nbsp; '
                f"<strong>{name}</strong><br><span class='note'>{detail}</span></div>",
                unsafe_allow_html=True,
            )

    eyebrow("Media server")
    server = MediaServer(config.media_server_port)
    running = server.already_running()
    left, right = st.columns([1, 3])
    with left:
        if st.button("Start media server", disabled=running):
            server.start()
            st.rerun()
    with right:
        state = "listening" if running else "not running"
        st.markdown(
            f'<div class="note" style="padding-top:0.5rem">Port {config.media_server_port}: '
            f"<span class='mono'>{state}</span>. Start this before ngrok, and point ngrok at "
            f"the same port.</div>",
            unsafe_allow_html=True,
        )

    eyebrow("Ground truth")
    truth = gt.load(config.ground_truth_path)
    if truth.available:
        st.markdown(
            f'<div class="okbox"><strong>Loaded from {truth.source}.</strong><br>'
            f"Facts on file: {', '.join(truth.known_keys())}<br>"
            f"<span class='note'>Still unknown: {', '.join(truth.missing_keys()) or 'nothing'}</span></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="warnbox"><strong>No ground truth on file.</strong><br>'
            "Findings that depend on real facts about the practice — office hours, accepted "
            "insurers, copay amounts — will be quarantined at gate 3 rather than scored. This "
            "is deliberate: without the facts, calling such a statement a bug would be a guess. "
            "Copy <span class='mono'>data/ground_truth.example.yaml</span> to "
            "<span class='mono'>data/ground_truth.yaml</span> and fill in what you learn from "
            "the agent or from the practice's own materials.</div>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

with tabs[1]:
    eyebrow("Catalogue")
    st.markdown(
        f'<div class="note">{len(SCENARIOS)} scenarios. Each is a hypothesis about the agent '
        "with named probes the caller must raise and named expectations the analyst measures "
        "against. Probe coverage is checked after every call, so a conversation that drifts "
        "off-target is visible rather than silently counted as a pass.</div>",
        unsafe_allow_html=True,
    )

    chosen = []
    for scenario in SCENARIOS:
        col_a, col_b = st.columns([1, 11])
        with col_a:
            include = st.checkbox(
                " ", value=scenario.id in st.session_state.selected,
                key=f"sel_{scenario.id}", label_visibility="collapsed",
            )
        with col_b:
            tags = "".join(f'<span class="tag">{t}</span>' for t in scenario.tags)
            st.markdown(
                f'<div class="panel"><strong>{scenario.id} &nbsp; {scenario.title}</strong>'
                f'<div style="margin:0.35rem 0">{tags}'
                f'<span class="tag">{scenario.category}</span></div>'
                f'<div class="note"><strong>Objective:</strong> {scenario.objective}</div>'
                f'<div class="note" style="margin-top:0.4rem"><strong>Probes:</strong> '
                + "; ".join(scenario.probes)
                + "</div>"
                f'<div class="note" style="margin-top:0.4rem"><strong>Expected of the agent:</strong> '
                + "; ".join(scenario.expectations)
                + "</div></div>",
                unsafe_allow_html=True,
            )
        if include:
            chosen.append(scenario.id)
    st.session_state.selected = chosen
    st.markdown(
        f'<div class="note"><strong>{len(chosen)} selected.</strong> The assessment requires a '
        "minimum of ten completed calls.</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def _worker(run_key: str, cfg: RunConfig, scenario_ids: list[str]) -> None:
    bus = RUN_BUS[run_key]

    def progress(level: str, message: str) -> None:
        bus["log"].append((datetime.now(timezone.utc).strftime("%H:%M:%S"), level, message))

    try:
        pipeline = Pipeline(cfg, progress, run_id=run_key)
        bus["run_id"] = pipeline.store.run_id
        pipeline.run(scenario_ids, analyse=True)
        bus["status"] = "done"
    except Exception as exc:  # noqa: BLE001
        progress("error", f"{type(exc).__name__}: {exc}")
        bus["status"] = "failed"


with tabs[2]:
    eyebrow("Execution")
    selected = st.session_state.selected
    blockers = config.missing_requirements()

    est_minutes = len(selected) * (config.policy.max_call_seconds + config.policy.inter_call_cooldown_seconds) / 60
    stat_row(
        [
            ("Scenarios queued", str(len(selected)), "sequential, one line"),
            ("Worst-case duration", f"{est_minutes:.0f}m", "most calls end sooner"),
            ("Target", config.target_number, "assessment line"),
            ("Analysis", "on", "every call analysed and verified"),
        ]
    )

    if blockers:
        st.markdown(
            '<div class="warnbox"><strong>Cannot start.</strong> Resolve the preflight items first.</div>',
            unsafe_allow_html=True,
        )
    elif len(selected) < 1:
        st.markdown('<div class="warnbox">Select at least one scenario.</div>', unsafe_allow_html=True)

    col_start, col_stop = st.columns([1, 5])
    with col_start:
        start = st.button("Start run", disabled=bool(blockers) or not selected or st.session_state.running)

    if start:
        run_key = RunStore().run_id
        RUN_BUS[run_key] = {"log": [], "status": "running", "run_id": run_key}
        st.session_state.run_id = run_key
        st.session_state.running = True
        threading.Thread(target=_worker, args=(run_key, config, list(selected)), daemon=True).start()
        st.rerun()

    active = st.session_state.run_id
    if active and active in RUN_BUS:
        bus = RUN_BUS[active]
        status = bus["status"]
        st.markdown(
            f'<div class="{"okbox" if status == "done" else "warnbox"}">'
            f'<strong>Run {active}</strong> — <span class="mono">{status}</span></div>',
            unsafe_allow_html=True,
        )

        eyebrow("Live log")
        body = "\n".join(f"{ts}  {lvl.upper():5s}  {msg}" for ts, lvl, msg in bus["log"][-400:])
        st.code(body or "Waiting for the first event.", language="text")

        if status == "running":
            import time as _time

            _time.sleep(3)
            st.rerun()
        else:
            st.session_state.running = False
            st.session_state.loaded_run = bus.get("run_id", active)


# ---------------------------------------------------------------------------
# Run loading helper
# ---------------------------------------------------------------------------

def run_selector(key: str) -> str | None:
    runs = RunStore.list_runs()
    if not runs:
        st.markdown(
            '<div class="note">No runs on disk yet. Complete a run, or drop an existing run '
            "directory into <span class='mono'>data/runs/</span>.</div>",
            unsafe_allow_html=True,
        )
        return None
    default = 0
    if st.session_state.loaded_run in runs:
        default = runs.index(st.session_state.loaded_run)
    return st.selectbox("Run", runs, index=default, key=key)


# ---------------------------------------------------------------------------
# Transcripts
# ---------------------------------------------------------------------------

with tabs[3]:
    eyebrow("Call record")
    run_id = run_selector("run_transcripts")
    if run_id:
        store = RunStore(run_id)
        calls = store.load_calls()
        if not calls:
            st.markdown('<div class="note">This run has no completed calls.</div>', unsafe_allow_html=True)
        else:
            labels = [f"{c['call_id']} — {c['scenario_id']}" for c in calls]
            picked = st.selectbox("Call", labels, key="tx_call")
            call = calls[labels.index(picked)]
            metrics = call["metrics"]

            stat_row(
                [
                    ("Duration", f"{metrics['duration_seconds']:.0f}s", "wall clock"),
                    ("Exchanges", str(metrics["exchanges"]), "agent then caller"),
                    (
                        "Median latency",
                        f"{metrics['median_response_latency']:.2f}s" if metrics["median_response_latency"] else "n/a",
                        "caller reply delay",
                    ),
                    ("Probe coverage", f"{metrics['probe_coverage']:.0%}", "scenario points raised"),
                    ("STT confidence", f"{metrics['mean_stt_confidence']:.3f}" if metrics["mean_stt_confidence"] else "n/a", "mean, agent turns"),
                    ("Barge-ins", str(metrics["barge_in_count"]), "caller yielded"),
                ]
            )

            recording = Path("data/recordings") / f"{call['call_id']}.mp3"
            if recording.exists():
                st.audio(str(recording))
            else:
                st.markdown(
                    '<div class="note">No recording on disk for this call. Twilio recordings can '
                    "take a minute to become available after a call ends.</div>",
                    unsafe_allow_html=True,
                )

            transcript_path = store.directory / call["call_id"] / f"{call['call_id']}_transcript.json"
            if transcript_path.exists():
                transcript = Transcript.from_dict(json.loads(transcript_path.read_text(encoding="utf-8")))
                cited = {f["turn_index"] for f in call.get("findings", [])}

                eyebrow("Turns")
                st.markdown(
                    '<div class="note">Turn indices are assigned once at capture and never '
                    "renumbered. Every finding cites one of these numbers. Turns marked CITED "
                    "are referenced by a finding.</div>",
                    unsafe_allow_html=True,
                )
                rows = []
                for turn in transcript.turns:
                    css = "agent" if turn.speaker == "AGENT" else "patient"
                    meta = []
                    if turn.response_latency:
                        meta.append(f"+{turn.response_latency:.2f}s")
                    if turn.interrupted:
                        meta.append("interrupted")
                    if turn.confidence is not None:
                        meta.append(f"conf {turn.confidence:.2f}")
                    if turn.index in cited:
                        meta.append("CITED")
                    rows.append(
                        f'<div class="turn {css}"><div class="idx">[{turn.index:03d}]</div>'
                        f'<div class="who">{turn.speaker}</div><div>{turn.text}'
                        f'<div class="meta">{" · ".join(meta)}</div></div></div>'
                    )
                st.markdown("".join(rows), unsafe_allow_html=True)

                if transcript.events:
                    eyebrow("Events")
                    st.code(
                        "\n".join(
                            f"{e.at}  {e.kind}"
                            + (f" (turn {e.turn_index})" if e.turn_index is not None else "")
                            + f": {e.detail}"
                            for e in transcript.events
                        ),
                        language="text",
                    )


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

with tabs[4]:
    eyebrow("Defects and their verification trail")
    run_id = run_selector("run_findings")
    if run_id:
        store = RunStore(run_id)
        calls = store.load_calls()
        findings = [(c, f) for c in calls for f in c.get("findings", [])]

        if not findings:
            st.markdown('<div class="note">No candidate findings in this run.</div>', unsafe_allow_html=True)
        else:
            counts = {
                status: sum(1 for _, f in findings if f["verification"]["status"] == status)
                for status in (STATUS_VERIFIED, STATUS_UNVERIFIED, STATUS_QUARANTINED, STATUS_REJECTED)
            }
            filtered = counts[STATUS_REJECTED] + counts[STATUS_UNVERIFIED]
            stat_row(
                [
                    ("Candidates", str(len(findings)), "proposed by the analyst"),
                    ("Verified", str(counts[STATUS_VERIFIED]), "cleared all four gates"),
                    ("Unverified", str(counts[STATUS_UNVERIFIED]), "adjudicator did not sustain"),
                    ("Quarantined", str(counts[STATUS_QUARANTINED]), "needs a fact not on file"),
                    ("Rejected", str(counts[STATUS_REJECTED]), "evidence absent from transcript"),
                    ("Filter rate", f"{filtered / len(findings):.0%}", "removed before scoring"),
                ]
            )

            col_a, col_b = st.columns(2)
            with col_a:
                status_filter = st.multiselect(
                    "Status",
                    [STATUS_VERIFIED, STATUS_UNVERIFIED, STATUS_QUARANTINED, STATUS_REJECTED],
                    default=[STATUS_VERIFIED, STATUS_UNVERIFIED, STATUS_QUARANTINED, STATUS_REJECTED],
                )
            with col_b:
                severity_filter = st.multiselect(
                    "Severity", list(SEVERITY_WEIGHTS), default=list(SEVERITY_WEIGHTS)
                )

            order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            findings.sort(key=lambda pair: (order.get(pair[1]["severity"], 9), pair[1]["id"]))

            for call, finding in findings:
                verification = finding["verification"]
                if verification["status"] not in status_filter or finding["severity"] not in severity_filter:
                    continue

                st.markdown(
                    f'<div class="panel flag-{verification["status"]}">'
                    f'<span class="tag {verification["status"]}">{verification["status"]}</span>'
                    f'<span class="tag {finding["severity"]}">{finding["severity"]}</span>'
                    f'<span class="tag">{finding["dimension"].replace("_", " ")}</span>'
                    f'<span class="tag">{finding["claim_type"]}</span>'
                    f'<span class="tag">confidence {verification["confidence"]:.2f}</span>'
                    f'<div style="margin-top:0.55rem;font-size:1.02rem;font-weight:600">{finding["title"]}</div>'
                    f'<div class="note" style="margin-top:0.3rem">'
                    f'<span class="mono">{finding["id"]}</span> &nbsp; '
                    f'{call["call_id"]} &nbsp; scenario {finding["scenario_id"]} &nbsp; turn {finding["turn_index"]}'
                    f"</div></div>",
                    unsafe_allow_html=True,
                )

                st.markdown(
                    f'<div class="quote">Agent, turn {finding["turn_index"]}: "{finding["evidence_quote"]}"</div>',
                    unsafe_allow_html=True,
                )

                left, right = st.columns(2)
                with left:
                    st.markdown(
                        f'<div class="note"><strong>What happened</strong><br>{finding["what_happened"]}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div class="note" style="margin-top:0.6rem"><strong>Why it matters</strong><br>'
                        f'{finding["why_it_matters"]}</div>',
                        unsafe_allow_html=True,
                    )
                with right:
                    st.markdown(
                        f'<div class="note"><strong>Expected instead</strong><br>'
                        f'{finding["expected_behaviour"]}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div class="note" style="margin-top:0.6rem"><strong>Outcome</strong><br>'
                        f'{verification["summary"]}</div>',
                        unsafe_allow_html=True,
                    )

                gate_strip(verification["gates"])

                votes = verification.get("adjudicator_votes", [])
                if votes:
                    with st.expander(
                        f"Adjudicator ballots — {len(votes)} independent samples, "
                        f"{verification['agreement_rate']:.0%} agreement"
                    ):
                        st.markdown(
                            '<div class="note">Each sample saw only the quote and two turns either '
                            "side. None saw the analyst's reasoning or its severity rating, so a "
                            "confidently argued but unsupported claim has nothing to lean on.</div>",
                            unsafe_allow_html=True,
                        )
                        for position, vote in enumerate(votes, start=1):
                            st.markdown(
                                f'<div class="panel"><span class="tag">sample {position}</span>'
                                f'<span class="tag">{vote["verdict"]}</span>'
                                f'<span class="tag">confidence {vote["confidence"]:.2f}</span>'
                                f'<div class="note" style="margin-top:0.45rem">{vote["reasoning"]}</div></div>',
                                unsafe_allow_html=True,
                            )
                st.markdown("<hr>", unsafe_allow_html=True)

            discarded = [d for c in calls for d in c.get("discarded_candidates", [])]
            if discarded:
                eyebrow("Discarded at extraction")
                st.markdown(
                    '<div class="note">These never became findings. They failed gate 1 on '
                    "structure before any adjudication ran, most often because the quote did not "
                    "exist in the transcript or cited a caller turn. Shown because a silently "
                    "dropped candidate is indistinguishable from one that was never proposed.</div>",
                    unsafe_allow_html=True,
                )
                for item in discarded:
                    st.markdown(
                        f'<div class="panel flag-rejected"><span class="tag rejected">discarded</span>'
                        f'<strong>{item["candidate"].get("title", "untitled")}</strong>'
                        f'<div class="note" style="margin-top:0.35rem">{item["reason"]}</div></div>',
                        unsafe_allow_html=True,
                    )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

with tabs[5]:
    eyebrow("Score derivation")
    run_id = run_selector("run_scoring")
    if run_id:
        store = RunStore(run_id)
        summary = store.load_summary()
        calls = store.load_calls()

        if not summary:
            st.markdown('<div class="note">This run has no summary yet.</div>', unsafe_allow_html=True)
        else:
            rs = summary["run_score"]
            stat_row(
                [
                    ("Calls scored", str(rs["calls_scored"]), "completed and analysed"),
                    ("Simulator quality", f"{rs['mean_simulator_score']:.0f}", "mean, out of 100"),
                    ("Agent quality", f"{rs['mean_agent_score']:.0f}", "mean, out of 100"),
                    ("Verified findings", str(rs["verification_counts"].get(STATUS_VERIFIED, 0)), "scored"),
                    ("Filter rate", f"{rs['hallucination_rate']:.0%}", "candidates removed"),
                ]
            )

            eyebrow("Run-level arithmetic")
            calc_block([(l["label"], l["expression"]) for l in rs["lines"]])

            eyebrow("Policy in force")
            st.markdown(
                '<div class="note">These weights are a stated policy, not a discovered truth. '
                "They live in one dictionary in <span class='mono'>src/scoring.py</span> so they "
                "can be argued with and changed.</div>",
                unsafe_allow_html=True,
            )
            col_a, col_b = st.columns(2)
            with col_a:
                calc_block(
                    [(f"{s.capitalize()} finding", f"-{w} points at full confidence")
                     for s, w in SEVERITY_WEIGHTS.items()],
                    ("Base score before deductions", str(BASE_SCORE)),
                )
            with col_b:
                calc_block(
                    [(DIMENSION_LABELS[d], f"weight {w:.2f}") for d, w in DIMENSION_WEIGHTS.items()],
                    ("Sum of weights", f"{sum(DIMENSION_WEIGHTS.values()):.2f}"),
                )

            st.markdown(
                f'<div class="note" style="margin-top:0.8rem">A finding deducts '
                f"<span class='mono'>severity weight x confidence</span> from its dimension. "
                f"Confidence is the adjudicator's mean confidence multiplied by its agreement "
                f"rate across samples, and anything below "
                f"<span class='mono'>{CONFIDENCE_THRESHOLD:.2f}</span> deducts nothing at all. "
                f"The composite is the weighted sum of the five dimension scores.</div>",
                unsafe_allow_html=True,
            )

            eyebrow("Per call")
            for call in calls:
                score = call["score"]
                with st.expander(
                    f"{call['call_id']} — {call['scenario_id']} — "
                    f"simulator {score['simulator_score']}/100, agent {score['agent_score']:.1f}/100"
                ):
                    st.markdown(
                        f'<div class="note"><strong>Simulator verdict.</strong> '
                        f'{score["simulator_verdict"]}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        '<div class="note" style="margin-top:0.5rem">Simulator gates are measured '
                        "from the call log. No model judgement is involved in any of these six "
                        "numbers.</div>",
                        unsafe_allow_html=True,
                    )
                    calc_block(
                        [
                            (
                                f"{g['name']} — {g['description']}",
                                f"{g['measured']} vs {g['threshold']} → "
                                f"{'PASS' if g['passed'] else 'FAIL'} → {g['points']}/{g['weight']}",
                            )
                            for g in score["simulator_gates"]
                        ],
                        ("Simulator quality", f"{score['simulator_score']} / 100"),
                    )

                    st.markdown('<div class="eyebrow">Agent dimensions</div>', unsafe_allow_html=True)
                    for dimension in score["dimension_scores"]:
                        lines = [(d["label"], d["expression"]) for d in dimension["deductions"]]
                        if not lines:
                            lines = [("No verified findings in this dimension", f"{BASE_SCORE} retained")]
                        calc_block(
                            [(f"Base", str(BASE_SCORE))] + lines,
                            (
                                f"{dimension['label']} at weight {dimension['weight']:.2f}",
                                f"{dimension['score']:.2f} x {dimension['weight']:.2f} = "
                                f"{dimension['weighted_contribution']:.2f}",
                            ),
                        )
                        st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)

                    calc_block(
                        [(l["label"], l["expression"]) for l in score["agent_lines"][:-1]],
                        (score["agent_lines"][-1]["label"], score["agent_lines"][-1]["expression"]),
                    )

                    if score["excluded"]:
                        st.markdown('<div class="eyebrow">Excluded from this score</div>', unsafe_allow_html=True)
                        for item in score["excluded"]:
                            st.markdown(
                                f'<div class="panel flag-{item["status"]}">'
                                f'<span class="tag {item["status"]}">{item["status"]}</span>'
                                f'<span class="tag {item["severity"]}">{item["severity"]}</span>'
                                f"<strong>{item['title']}</strong>"
                                f'<div class="note" style="margin-top:0.35rem">{item["reason"]}</div>'
                                f'<div class="note">Had it been verified at full confidence it would '
                                f'have cost {item["would_have_deducted"]:.2f} composite points.</div></div>',
                                unsafe_allow_html=True,
                            )


# ---------------------------------------------------------------------------
# Method
# ---------------------------------------------------------------------------

with tabs[6]:
    eyebrow("How a call becomes a number")
    st.markdown(
        """
<div class="note" style="max-width:52rem">

**1. The call.** Twilio dials the line under test and bridges the audio into a local
websocket. Inbound audio streams to Deepgram; settled utterances become AGENT turns with
a fixed index. A Claude-driven caller with a persona, an objective and a list of probes
generates each reply, which is synthesised to 8 kHz mu-law and paced back down the wire
in 20 ms frames. Pacing rather than bulk-sending is what makes barge-in possible: audio
already sitting in Twilio's jitter buffer cannot be recalled.

**2. The record.** Turn indices are assigned once and never renumbered. Speaker
attribution is structural — the harness generated the caller audio, so anything on the
inbound track is the agent. There is no diarisation step to get wrong.

**3. Measured metrics.** Duration, exchange count, latency distribution, barge-in count,
transcription confidence and probe coverage are counted from the log. No model is asked
anything. These produce the simulator quality score, which answers "was this call good
enough to draw conclusions from" separately from "was the agent any good".

**4. Candidate findings.** An analyst model reads the transcript against the scenario's
stated expectations and proposes defects. Every candidate must name a turn index, quote
that turn verbatim, and declare whether the claim is behavioural or factual.

**5. Four gates.** Structure, then a deterministic verbatim match, then fact dependency,
then independent adjudication sampled several times. The verbatim match is the important
one and it involves no model at all: a quote that is not in the transcript kills the
finding outright, which removes the most common failure in model-graded QA — a plausible
bug supported by words nobody said.

**6. Scoring.** Verified findings deduct severity weight times confidence from their
dimension. Confidence is adjudicator confidence times sample agreement. Unverified,
quarantined and rejected findings deduct nothing but are still reported.

</div>
        """,
        unsafe_allow_html=True,
    )

    eyebrow("What this system refuses to do")
    st.markdown(
        """
<div class="note" style="max-width:52rem">

It will not call a factual statement wrong without the fact on file. If the agent says
the practice opens at seven and no ground truth has been supplied, that is quarantined at
gate 3, not scored. The alternative — letting a model decide what a clinic's opening hours
probably are — is how QA tooling generates confident fiction.

It will not let a finding survive on fluent reasoning. The adjudicator sees the quote and
its immediate neighbours, never the analyst's argument.

It will not hide what it discarded. Rejected candidates, quarantined claims and the
extraction-stage discards all appear in the interface and in the exported report, with
reasons.

It will not treat a failed adjudication call as agreement. An API error returns
INSUFFICIENT, which lowers the agreement rate rather than quietly passing.

</div>
        """,
        unsafe_allow_html=True,
    )

    eyebrow("Known limitations")
    st.markdown(
        """
<div class="note" style="max-width:52rem">

Transcription errors propagate. If Deepgram mishears the agent, the analyst reads the
mistake as fact. Mean confidence per call is surfaced so a low-quality transcript can be
discounted, but the harness cannot detect a confident mistranscription.

The cascade costs latency. Speech to text, then reasoning, then text to speech runs
roughly 300 to 500 ms slower per turn than a speech-to-speech model. That is the price of
a citable transcript and independently tunable turn-taking, and it was paid deliberately.

Severity weights are a judgement call. They are visible and editable rather than
defensible from first principles.

Sample agreement measures stability, not correctness. Three samples that agree on a wrong
answer will still produce high confidence. It catches instability, not shared bias.

</div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

with tabs[7]:
    eyebrow("Deliverables")
    run_id = run_selector("run_export")
    if run_id:
        store = RunStore(run_id)
        calls = store.load_calls()
        summary = store.load_summary()

        if summary and calls:
            findings: list[Finding] = []
            for call in calls:
                for raw in call.get("findings", []):
                    verification = raw.pop("verification", {})
                    finding = Finding(**raw)
                    finding.verification = verification
                    raw["verification"] = verification
                    findings.append(finding)

            from src.scoring import CallScore  # local import keeps module load light

            run_score = score_run([], [])
            report = build_bug_report(run_id, calls, run_score)

            st.download_button(
                "Download bug report (Markdown)",
                data=report,
                file_name=f"bug_report_{run_id}.md",
                mime="text/markdown",
            )
            st.download_button(
                "Download run summary (JSON)",
                data=json.dumps(summary, indent=2),
                file_name=f"summary_{run_id}.json",
                mime="application/json",
            )

            eyebrow("Files on disk")
            rows = []
            for call in calls:
                call_dir = store.directory / call["call_id"]
                recording = Path("data/recordings") / f"{call['call_id']}.mp3"
                rows.append(
                    f"{call['call_id']:24s}  transcript: {'yes' if call_dir.exists() else 'no':3s}  "
                    f"recording: {'yes' if recording.exists() else 'no':3s}  "
                    f"turns: {call['metrics']['total_turns']:3d}  "
                    f"findings: {len(call.get('findings', [])):2d}"
                )
            st.code("\n".join(rows), language="text")

            st.markdown(
                f'<div class="note">Transcripts live under '
                f"<span class='mono'>data/runs/{run_id}/</span> as both JSON and plain text. "
                f"Recordings are in <span class='mono'>data/recordings/</span> as MP3. Both "
                f"directories are what you commit alongside the bug report.</div>",
                unsafe_allow_html=True,
            )

            eyebrow("Submission checklist")
            completed = len([c for c in calls if c["metrics"]["exchanges"] >= 3])
            with_recording = len([c for c in calls if (Path("data/recordings") / f"{c['call_id']}.mp3").exists()])
            checks = [
                ("Calls with a real conversation (3+ exchanges)", f"{completed} of 10 required"),
                ("Calls with an audio recording on disk", f"{with_recording} of {len(calls)}"),
                ("Transcripts written", f"{len(calls)}"),
                ("Bug report generated", "yes" if report else "no"),
                ("Loom walkthrough", "record separately"),
                ("Loom AI-debugging video", "record separately"),
            ]
            calc_block(checks)
