# Voice QA Harness

An automated caller that telephones an AI voice agent, holds a realistic
patient conversation, and produces evidence-backed defect reports.

Built against the Pretty Good AI test line, `+1-805-439-8008`.

**What it does**

- Places real outbound calls through Twilio and speaks with a synthesised voice
- Drives each call with a Claude-powered patient persona that steers toward a
  stated objective rather than reading a script
- Handles barge-in, interruptions, silence and disorientation as testable
  conditions
- Records audio (MP3) and produces speaker-attributed transcripts with stable
  turn indices
- Analyses each call for defects, then puts every candidate through four
  verification gates before it can affect a score
- Reports what it discarded and why, alongside what it kept

---

## Setup

### 1. Python

Requires Python 3.10 or newer.

```bash
git clone <your-repo-url>
cd voice-qa
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Accounts

Four services. All have free or trial tiers; a full twelve-call run costs
roughly $10.

| Service | Purpose | Where to get the key |
| --- | --- | --- |
| Twilio | Places the calls | console.twilio.com, Account Info panel |
| Anthropic | Caller brain, analyst, adjudicator | console.anthropic.com, API Keys |
| Deepgram | Live speech to text | console.deepgram.com, API Keys |
| ElevenLabs | Caller voice | elevenlabs.io, Profile, API Key |

You also need a **voice-capable Twilio phone number**. Buy one under Phone
Numbers, Manage, Buy a number, with the Voice capability ticked. This is the
single number all test calls originate from and the one you report on the
submission form.

> Twilio trial accounts can only call verified numbers. Verify
> `+18054398008` under Phone Numbers, Manage, Verified Caller IDs, or upgrade
> the account. A trial account will otherwise fail to connect.

### 3. Configuration

```bash
cp .env.example .env
```

Fill in `.env`. Alternatively, paste the keys straight into the dashboard
sidebar — they stay in memory and are never written to disk either way.

### 4. Public tunnel

Twilio needs to reach your machine. Install ngrok from ngrok.com, add your
authtoken, then:

```bash
# terminal 1 — media server
python -m uvicorn src.media_server:app --host 0.0.0.0 --port 8080

# terminal 2 — tunnel
ngrok http 8080
```

Copy the forwarding host — the part after `https://`, with no trailing slash —
into `PUBLIC_BASE_URL` or the dashboard's ngrok field.

> The free ngrok URL changes every restart. If calls connect and then go
> silent, a stale URL is the usual cause.

---

## Running

### Dashboard

```bash
streamlit run dashboard.py
```

Opens on `http://localhost:8501`. Work through the tabs left to right:
**Preflight** to verify credentials with live checks, **Scenarios** to choose
what to run, **Run** to execute, then **Transcripts**, **Findings** and
**Scoring** to read the results.

### Command line

```bash
python run_batch.py --list                      # show the catalogue
python run_batch.py --scenarios S01             # one call, to prove the path works
python run_batch.py                             # the default twelve
python run_batch.py --all                       # everything
python run_batch.py --reanalyse run_20260826_1015  # re-score stored transcripts
```

**Make one call first.** Confirm the audio sounds right before spending money
on a batch.

---

## Output

```
data/
  runs/<run_id>/
    config.json                       credentials redacted
    summary.json                      run-level scores
    bug_report.md                     the deliverable
    <call_id>/
      <call_id>_transcript.txt        human readable
      <call_id>_transcript.json       machine readable, stable turn indices
      analysis.json                   findings with full gate trails
  recordings/
    <call_id>.mp3                     dual-channel audio
```

---

## Ground truth

The harness will not call a factual statement wrong without the fact on
record. If the agent says the clinic opens at seven and nothing is on file
about opening hours, that finding is **quarantined**, not scored.

This is deliberate. Letting a model decide what a clinic's hours probably are
is how QA tooling produces confident fiction.

To score those findings:

```bash
cp data/ground_truth.example.yaml data/ground_truth.yaml
# fill in only what you can actually confirm
python run_batch.py --reanalyse <run_id>
```

Re-analysis works on stored transcripts, so no new calls are placed.

---

## How a finding survives

Four gates. A finding that fails any gate contributes nothing to any score,
and is still reported with the reason.

| Gate | Check | Model involved |
| --- | --- | --- |
| 1 | Schema, turn range, cites an AGENT turn | no |
| 2 | Quote appears verbatim in the cited turn | no |
| 3 | Any required external fact is on file | no |
| 4 | Independent adjudicator sustains the claim across N samples | yes |

Gate 2 is the important one. A quote that is not in the transcript kills the
finding outright, which removes the most common failure in model-graded QA: a
plausible bug supported by words nobody said.

Confidence is the adjudicator's mean confidence multiplied by its agreement
rate across samples. Below 0.55, a finding deducts nothing.

---

## Troubleshooting

**Call connects, then silence.** The ngrok URL is stale or points at the wrong
port. Check `https://<your-host>/health` returns JSON. Restart the media
server before ngrok, not after.

**"Cannot connect to media server".** It is not running. Start it in its own
terminal, or use the Preflight tab's start button.

**Bot talks over the agent constantly.** Endpointing is too low. Raise it
toward 400–500 ms in the dashboard's model settings.

**Long gaps before the bot replies.** Check the Transcripts tab for median
latency. Above 2.5 s, switch the caller model to a faster one, or confirm
ElevenLabs is the TTS provider — the OpenAI fallback transcodes and is slower.

**Calls fail immediately.** On a Twilio trial account, verify the target
number or upgrade. Check Twilio's console error log for the specific code.

**No recording appears.** Twilio takes up to a minute to make recordings
available. The fetcher polls for a minute; if it gives up, the call SID is in
the transcript JSON and the recording can be pulled manually.

**Findings all come back quarantined.** Expected with no ground truth. See
above.

---

## Tests

```bash
pytest test_pipeline.py -q
```

Covers the codec, evidence matching and scoring arithmetic — the three places
where a silent bug would invalidate output rather than merely break it. The
realtime path needs a live call to verify.

---

## Further reading

- `ARCHITECTURE.md` — how the system works
- `CONTEXT.md` — why it is built this way, and what was rejected
- `CLAUDE.md` — invariants for anyone (or anything) editing the code
