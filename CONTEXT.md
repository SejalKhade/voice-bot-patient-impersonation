# CONTEXT.md

Why this system is shaped the way it is. Read `ARCHITECTURE.md` for how it
works; this file is about the decisions and the ones that were rejected.

## The problem

Build a bot that telephones an AI voice agent, behaves like a patient, and
finds bugs. The brief is explicit that voice quality is judged first: a
submission whose bot cannot hold a coherent conversation is rejected before
the code is read. It also asks for "active steering toward the intended
test-case outcome" and warns against sounding like "a scripted benchmark
runner".

That framing drives most of what follows. A harness that makes ten technically
successful calls where the bot sounds robotic has failed the primary bar. So
naturalness and turn-taking got more attention than breadth of features.

## Decision 1: cascade, not speech-to-speech

The obvious alternative was a realtime speech-to-speech API. It would be
lower latency and less code. Rejected for three reasons, in order of weight.

**The transcript is the deliverable.** Bugs must be cited to specific turns
with verbatim quotes. A cascade produces a timestamped, speaker-attributed
record as a by-product. Getting the same from a speech-to-speech model means
bolting transcription back on, which is the cascade again with extra steps.

**Control over the things being tested.** The brief asks for barge-in and
interruption scenarios. Endpointing thresholds, barge-in sensitivity and turn
policy are all parameters here, exposed in the dashboard. A realtime API hides
them behind vendor defaults, which makes "test the agent's turn-taking" hard
to do deliberately.

**Attribution when something sounds wrong.** With separate components, a bad
call can be traced to STT, the brain, or TTS. One opaque model makes that
undiagnosable, and the brief explicitly asks for evidence of iteration.

The cost is real: roughly 300–500 ms more per turn. Mitigated by using
ElevenLabs' `ulaw_8000` output, which removes a transcode from the loop, and a
small fast model for the caller with a tight token ceiling. Median latency in
practice sits near 1.5 s, which reads as a normal phone pause.

## Decision 2: a stateful caller, not a script

A script cannot steer. It says line three regardless of what it heard, which
is precisely the "scripted benchmark runner" the brief warns against. But a
free-form role-player wanders and lands maybe half the points a scenario
exists to test.

The compromise: each scenario declares `probes` — things the caller must
actually raise — and the brain is told each turn which remain outstanding.
Wording stays generated fresh against what the agent just said; the agenda
stays fixed. Coverage is measured after the call, so a conversation that
drifted is visible in the metrics rather than quietly counted as a pass.

## Decision 3: the hallucination guard

This is the part that took the most thought, and the reason is worth stating
plainly: **an LLM asked to find bugs will find bugs, whether or not any
exist.** It will produce a fluent, plausible, well-structured report about
things that did not happen. A QA tool that does this is worse than no tool,
because it looks authoritative.

Four gates, in order:

1. **Structure.** Fields present, turn index in range, cites an AGENT turn,
   severity and dimension from the allowed sets.
2. **Evidence grounding.** The quote is normalised and matched against the
   cited turn. **No model is involved.** A quote that is not in the transcript
   kills the finding outright. This single string comparison removes the most
   common failure mode, and it is deterministic, so it cannot itself be
   talked around.
3. **Fact dependency.** Behavioural claims (self-contradiction, ignoring a
   stated constraint, failing to confirm a booking) are provable from the
   transcript. Factual claims (office hours, insurers, copay) are not. Without
   the matching fact in `ground_truth.yaml`, the finding is quarantined, not
   scored.
4. **Independent adjudication.** A separate model sees only the quote and two
   turns either side — never the analyst's reasoning or severity. It is
   sampled several times and disagreement between samples discounts
   confidence.

Gate 3 deserves defending because it will feel over-cautious. The assessment's
own example bug is *"agent confirms appointment for Sunday, but the practice
is closed on weekends"*. That is only a bug if the practice really is closed
at weekends. Absent that fact, asserting it is a guess dressed as a finding.
Supply the fact in `ground_truth.yaml` and re-run analysis; the quarantined
finding becomes scoreable without re-dialling.

**What the guard does not do:** it measures stability, not truth. Three
samples that agree on a wrong answer still yield high confidence. It catches
instability and fabricated evidence, not shared bias.

## Decision 4: two scores, never blended

*Simulator quality* answers "was this call good enough to draw conclusions
from" and is measured from logs with no model judgement. *Agent quality*
answers "was the agent any good" and derives only from verified findings.

Blending them would let a broken harness flatter the agent, or a clean harness
hide a bad one. It would also make the primary evaluation bar — does the bot
hold a coherent conversation — invisible. Any call scoring below 60 on
simulator quality should be re-run, not analysed.

## Decision 5: sequential calls, single number

The brief requires one originating number for all test calls. Two concurrent
calls from one number would either collide at the far end or produce latency
figures that mean nothing. Sequential with a cooldown, guarded by a watchdog
that hangs up on dead air.

## What was deliberately left out

- **Production infrastructure.** No queue, no database, no container. The
  brief says explicitly it is not looking for this. Runs are JSON on disk,
  readable without running anything.
- **Concurrency.** See above.
- **Retry-until-success.** A failed call is recorded as a failed call. Hiding
  flakiness would hide real information about the agent.
- **Automatic ground truth inference.** Tempting and wrong. See gate 3.

## Known limitations

- Transcription errors propagate. If Deepgram mishears the agent, the analyst
  treats the mistake as fact. Mean confidence per call is surfaced so a poor
  transcript can be discounted, but a confident mistranscription is
  undetectable from inside the system.
- Severity weights are a judgement call, visible and editable in
  `src/scoring.py` rather than defensible from first principles.
- The caller's own imperfections are excluded from findings by instruction,
  not by mechanism. A sufficiently confused analyst could still blame the
  agent for the harness's mistakes.
- Probe coverage is checked by a model reading what the caller said. It is
  the one place a model judges the harness's own performance.
- Endpointing (`endpointing_ms`, raised 320ms -> 700ms after a live call
  showed it firing mid-sentence throughout) still occasionally cuts the
  agent off during its opening exchange specifically - two calls out of
  four show a short fragment ("Before we can look for appoint...") right
  as the agent begins a multi-clause opening line, most likely a pause
  longer than 700ms while it does some initial lookup. Deepgram's
  confidence on these fragments is 0.99+, so it is a real cutoff, not a
  mishearing. Raising the threshold further trades this away against
  dead air on every other turn in every other call, which is the worse
  failure mode - left as a known, contained limitation rather than
  chased to zero.
