# Architecture

## How it works

A run has two halves that never touch each other's state. The **realtime half**
places a call and produces a transcript; the **analysis half** reads stored
transcripts and produces scored findings. Analysis can be re-run at any time
without dialling anything, which matters because supplying ground truth turns
previously unscoreable findings into scoreable ones.

For each call, Twilio dials the line under test and bridges the audio into a
websocket on a local FastAPI server. Inbound audio — everything the agent says
— streams to Deepgram, which returns settled utterances that become AGENT
turns with a fixed index. Each utterance goes to a Claude-driven caller that
holds a persona, an objective and a list of probes it must raise; its reply is
synthesised by ElevenLabs directly to 8 kHz mu-law and paced back down the
wire in 20 ms frames. Pacing rather than bulk-sending is what keeps barge-in
possible: audio already sitting in Twilio's jitter buffer cannot be recalled,
so a bulk send silently disables interruption handling. When Deepgram reports
the agent speaking mid-playback, the server sends a `clear` event and abandons
the rest of the utterance. A watchdog ends calls on dead air or overrun.

Afterwards, deterministic metrics are counted from the log — duration, turn
count, latency distribution, barge-ins, transcription confidence, probe
coverage — with no model involved. These produce a **simulator quality**
score, which answers "was this call good enough to draw conclusions from"
separately from "was the agent any good". An analyst model then proposes
candidate defects, each of which must cite a turn index and quote it verbatim.
Every candidate passes through four gates: structure, a deterministic verbatim
match against the transcript, a fact-dependency check, and independent
adjudication sampled several times by a model that sees only the quote and its
immediate neighbours. Survivors deduct `severity weight × confidence` from
their quality dimension; everything else is reported but deducts nothing.

```
  Twilio ──ws──► media_server ──ws──► Deepgram          [inbound: the agent]
                      │
                      ▼
              PatientBrain (Claude)                     [persona + probes]
                      │
                      ▼
  Twilio ◄──ws── media_server ◄─https── ElevenLabs      [outbound: the caller]
                      │
                      ▼
                 Transcript ──► metrics ──► simulator score
                      │
                      └──────► analyst ──► 4 gates ──► agent score
```

## Key design choices

**Cascade over speech-to-speech.** A realtime speech-to-speech API would be
lower latency and less code. Three things outweighed that. The transcript is
the deliverable — every bug must cite a turn and quote it verbatim, which a
cascade gives for free. The brief asks specifically for barge-in and
interruption testing, and endpointing, barge-in sensitivity and turn policy
are all parameters here rather than vendor defaults. And when a call sounds
wrong, separate components make it traceable to STT, the brain, or TTS,
whereas one opaque model makes that undiagnosable. The cost is roughly
300–500 ms extra per turn, reduced by ElevenLabs' native `ulaw_8000` output
(no transcode in the loop) and a small fast model for the caller. Median
latency lands near 1.5 s, which reads as a normal phone pause.

**A steered caller, not a script.** A script cannot react, which is exactly
the "scripted benchmark runner" the brief warns against; a free-form
role-player wanders and misses half the points a scenario exists to test. Each
scenario declares probes the caller must raise, and the brain is told each
turn which remain outstanding. Wording stays generated fresh; the agenda stays
fixed. Coverage is measured afterwards, so drift shows up in the metrics
rather than passing silently.

**Separate process for the media server.** Streamlit re-executes its script on
every widget interaction, which would kill a websocket holding a live call.
The server runs as its own uvicorn process; the dashboard talks to it over
loopback and polls for state. The CLI uses the same path, which keeps the
dashboard from accumulating logic nothing else can reach.

**Evidence gating over model confidence.** A model asked to find bugs will
find bugs whether or not any exist, and it will write them up fluently. The
load-bearing defence is gate 2, a deterministic string match with no model in
it: a quote that is not in the transcript kills the finding. Gate 3 handles
the subtler case — claims that depend on facts about the practice the system
was never told. Those are quarantined rather than scored, because asserting a
clinic's opening hours from a language model's priors is how QA tooling
generates confident fiction. Gate 4 samples an independent adjudicator that
never sees the analyst's reasoning, so a well-argued but unsupported claim has
nothing to lean on; disagreement across samples discounts confidence rather
than being averaged away.

**Two scores, never blended.** Simulator quality is measured; agent quality is
judged from verified findings only. Merging them would let a broken harness
flatter the agent, and would hide the assessment's own primary bar — whether
the bot holds a coherent conversation — inside a composite number.

## Component map

| Module | Responsibility |
| --- | --- |
| `audio.py` | G.711 mu-law codec, resampling, Twilio frame geometry |
| `stt.py` | Deepgram live transcription over a raw websocket |
| `tts.py` | Synthesis to Twilio-ready mu-law; ElevenLabs primary, OpenAI fallback |
| `patient.py` | The caller: persona, objective, probe steering, turn generation |
| `media_server.py` | Twilio webhooks, the audio bridge, barge-in, watchdog |
| `transcript.py` | Turn model with stable indices; verbatim matching primitives |
| `metrics.py` | Counted metrics and the simulator quality gates |
| `analyzer.py` | Candidate defect extraction with a strict output contract |
| `verifier.py` | The four gates |
| `scoring.py` | Deduction arithmetic, emitted as displayable expressions |
| `ground_truth.py` | Optional facts; honest handling of their absence |
| `store.py` | Run persistence and bug report generation |
| `orchestrator.py` | Server supervision and the run loop |

## Failure handling

The watchdog hangs up on 18 seconds of dead air or on exceeding the call
duration cap, so a stuck call cannot burn telephony credit unattended. TTS
failures are recorded as call events and surface in the metrics rather than
crashing the turn loop. A failed adjudicator call returns `INSUFFICIENT`,
never `SUPPORTED` — an API error must lower confidence, not pass silently. A
failed call is recorded as a failed call; there is no retry-until-success,
because hiding flakiness would hide real information about the agent.
