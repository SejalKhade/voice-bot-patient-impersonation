# CLAUDE.md

Working notes for an AI assistant editing this repository. Read this before
changing anything.

## What this is

A test harness that telephones an AI voice agent, holds a realistic patient
conversation with it, and produces evidence-backed defect reports. Built for
the Pretty Good AI engineering assessment. The line under test is
`+1-805-439-8008`.

Two halves that should stay separable:

- **Realtime** (`src/media_server.py`, `stt.py`, `tts.py`, `patient.py`,
  `audio.py`) holds phone calls open. Latency-sensitive, async throughout.
- **Analysis** (`analyzer.py`, `verifier.py`, `scoring.py`, `metrics.py`,
  `store.py`) reads stored transcripts. Offline, synchronous, reproducible.

Analysis can always be re-run over stored transcripts without placing calls
(`python run_batch.py --reanalyse <run_id>`). Keep it that way. Anything that
makes analysis depend on live call state breaks the ability to re-score after
supplying ground truth.

## Invariants

These are not style preferences. Breaking one silently invalidates the output.

1. **Turn indices are assigned once at capture and never renumbered.** Every
   finding, gate and report cites them. Merging, reordering or filtering turns
   after capture makes every stored citation point at the wrong thing.

2. **Speaker attribution is structural, never inferred.** The harness
   generates the caller audio, so it knows what it said; anything on the
   inbound Twilio track is the agent. Do not add diarisation.

3. **A finding cannot affect a score without a verbatim quote that matches
   its cited turn.** `transcript.contains_verbatim` is the load-bearing check
   and it involves no model. Do not relax it to fuzzy or semantic matching.

4. **Factual claims need the fact on file.** If `data/ground_truth.yaml` does
   not contain the required key, the finding is quarantined at gate 3, not
   scored. Do not add a fallback that lets a model supply the fact.

5. **A failed adjudicator call returns `INSUFFICIENT`, never `SUPPORTED`.**
   An API error must lower confidence, not pass silently.

6. **Simulator quality and agent quality never merge.** They answer different
   questions and have different owners. A single blended number would let a
   broken harness flatter the agent.

7. **Secrets never reach disk.** `RunConfig.redacted()` strips them before
   anything is serialised. If you add a credential field, add it to
   `SECRET_FIELDS` in `config.py` in the same commit.

## Audio, specifically

Twilio speaks 8 kHz mono G.711 mu-law, base64, 160-byte frames. `audio.py`
implements the codec in numpy against the ITU reference.

The encoder works in a **14-bit domain** (input shifted right by two, clip
8159, bias 33, mantissa shift `seg + 1`). The decoder returns **16-bit**
(bias 132, mantissa shift 3). Mixing the domains produces audio four times
too loud, which clips into distortion and wrecks the far end's own speech
recognition. This bug was in the first version and the tests exist to catch
its return. If you touch `pcm16_to_mulaw`, run `pytest test_pipeline.py`
before anything else.

Outbound frames are **paced in real time**, one per 20 ms. Twilio will accept
a whole buffer at once, but audio already in its jitter buffer cannot be
recalled, so bulk-sending silently disables barge-in. Do not "optimise" the
pacing loop away.

## Conventions

- No emojis anywhere, including commit messages and the dashboard.
- Comments explain *why*, not *what*. If a comment restates the code, delete it.
- Prose in the dashboard and reports is plain English. No marketing register.
- New scenarios go in `src/scenarios.py` and need `probes` (what the caller
  must say) and `expectations` (what a competent receptionist would do). The
  analyst measures only against `expectations`.
- Model names live in `ModelConfig` and are user-editable in the dashboard.
  Do not hard-code them elsewhere.

## Testing

`pytest test_pipeline.py` covers the three places where a silent bug invalidates
everything downstream: the codec, evidence matching, and scoring arithmetic.
It does not cover the realtime path, which needs a live call. Verify that
with a single real call (`python run_batch.py --scenarios S01`) before any
batch.

## Cost

Roughly $0.60 to $1.20 per call, dominated by telephony and TTS. A twelve-call
run lands around $10. The adjudicator samples every finding N times, so
raising `adjudicator_samples` raises cost proportionally on the analysis side.
Guard rails are in `CallPolicy`: keep `max_call_seconds` and
`silence_timeout_seconds` in place.
