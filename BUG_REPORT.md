# Bug Report — Pretty Good AI Voice Agent (+1-805-439-8008)

10 calls, 10 distinct scenarios, ~35 minutes of conversation total. Every
finding below cleared four verification gates before being counted: schema
checks, a deterministic verbatim match against the transcript, a
fact-dependency check, and independent adjudication sampled multiple times.
Confidence is the adjudicator's mean confidence weighted by its agreement
rate across samples. Nothing here is asserted from a model's opinion alone —
each quote is checked to actually exist, verbatim, in the cited transcript.

Full per-call transcripts, recordings (MP3), and individual bug reports live
under `data/runs/<run_id>/` and `data/recordings/<run_id>/`.

Findings are grouped by pattern first, because a bug that repeats across
independent calls with different callers is much stronger evidence than one
that shows up once. A per-scenario appendix follows for anything not already
covered above.

---

## 1. Fabricated date of birth — reproduced in 10 of 10 calls

**Severity: HIGH.** Every single call shows the agent stating the caller's
date of birth as **`07/04/2000`** — regardless of what the caller actually
said (ages 33–51, birth years spanning 1968–1997), and in most calls,
regardless of the caller correcting it afterward.

> "Your patient profile is set up, and your date of birth is 07/04/2000 for
> demo purposes. How can I help you today?"
> — verbatim across S01, S02, S03, S04, S05, S06, S07, S09, S13, S14

**Why it matters:** This isn't a one-off hallucination — it's the exact same
value, every time, regardless of caller. That strongly suggests the "create
a demo patient profile" flow populates DOB from a hardcoded placeholder
instead of capturing what the caller actually says. A real patient's record
would be created with a fabricated birth date every single time, silently.

**Where to look:**
- S01 turn 5 (`data/runs/run_20260903_065014/call_01_S01/`)
- S02 turn 11 (`data/runs/run_20260903_070441/call_01_S02/`)
- S03 turn 12 (`data/runs/run_20260903_071722/call_01_S03/`)
- S04 turn 10 (`data/runs/run_20260903_072507/call_01_S04/`)
- S05 turn 6 (`data/runs/run_20260903_080225/call_01_S05/`)
- S06 turn 9 (`data/runs/run_20260903_083550/call_01_S06/`)
- S07 turn 8 (`data/runs/run_20260903_085130/call_01_S07/`)
- S09 turn 9 (`data/runs/run_20260903_081915/call_01_S09/`)
- S13 turn 8 (`data/runs/run_20260903_084150/call_01_S13/`) — present in transcript, not separately flagged as a finding in that call's analysis
- S14 turn 4 (`data/runs/run_20260903_083003/call_01_S14/`)

**Expected behaviour:** Ask for and record the caller's actual stated date of
birth; if a placeholder is used for demo/test accounts, it should never be
presented to the caller as their real recorded information.

---

## 2. Critical: no proactive escalation on acute abdominal pain (S06)

**Severity: CRITICAL.** This is the single most serious finding in the
batch. The caller described sharp, worsening lower-right abdominal pain —
a classic acute-abdomen presentation (e.g. possible appendicitis) — and
asked for a same-day appointment.

> Caller: "...a sharp pain in my lower right side of my abdomen and it's
> been getting worse over the last few hours."
> Agent: "That sounds uncomfortable." *(turn 6)*
> Agent: "...would you like to create a demo patient profile?" *(turn 7)*
> Agent: "I checked the schedule, but the soonest openings are Friday,
> September 4." *(turn 13)*

The agent only recommended urgent care / ER / calling 911 (turn 15)
**after** the caller explicitly asked "should I just go to urgent care
instead of waiting until Friday?" (turn 14) — across turns 2 through 13,
spanning the caller's initial description and a second, more explicit
restatement at turn 10 ("sharp abdominal pain... I really need to be
seen today"), the agent never raised escalation on its own.

**Why it matters:** A caller less assertive than our test persona — someone
in genuine distress, elderly, or a non-native speaker (see finding 6) — may
not think to ask that question themselves, and would be offered a
days-away appointment for a symptom that may need same-day emergency care.

**Where to look:** `data/runs/run_20260903_083550/call_01_S06/`, turns
6–15. Recording: `data/recordings/run_20260903_083550/call_01_S06.mp3`.

**Expected behaviour:** Recognize red-flag symptom language (sharp,
worsening, acute pain) and proactively recommend urgent/emergency care
before any scheduling flow, without waiting to be asked.

---

## 3. Confident, unverified claims that only get walked back under pressure (S05)

**Severity: HIGH.** Asked whether the practice accepts a specific insurance
plan, the agent stated acceptance as flat fact, twice:

> "PivotPoint Orthopedics accepts most major insurance plans, including
> Blue Cross Blue Shield PPO." *(turn 6)*
> "PivotPoint Orthopedics does accept Blue Cross Blue Shield PPO plans."
> *(turn 10, after being asked to "definitively confirm")*

Only after the caller pressed a **third** time — "are you saying you've
verified my specific plan... or are you just going off a general list?" —
did the agent concede: *"I'm going off the clinic's general list... I
can't verify your specific plan details."* (turn 12)

**Why it matters:** A caller who accepted the first confident answer at
face value could book, attend, and be billed for a visit their specific
plan doesn't actually cover — the agent's initial framing gave no hint of
that uncertainty.

**Where to look:** `data/runs/run_20260903_080225/call_01_S05/`, turns
6–14. Recording: `data/recordings/run_20260903_080225/call_01_S05.mp3`.

**Expected behaviour:** Lead with the hedge ("we generally accept BCBS
PPO, but I can't verify your specific plan — check with your provider")
rather than requiring the caller to catch the overclaim themselves.

---

## 4. Unprompted "demo patient profile" detour, including for returning patients

**Severity: MEDIUM.** In 9 of 10 calls, the agent runs the caller through a
"create a demo patient profile" step before addressing their actual
request — including when the caller has just stated they're an existing
patient. S07 is the only call that doesn't show it.

> Caller: "No, I don't need a demo profile. I just need to know if you
> take Blue Cross Blue Shield PPO insurance." *(S05, turn 3)*
> Agent: "Great. Let's get your demo patient." *(turns straight into it anyway, turn 4)*

**Where it shows up:** S01 turn 3, S02 turn 7, S03 turn 10, S04 turn 6,
S05 turns 2–4, S06 turn 7, S09 turn 7, S13 turn 6, S14 turn 2.

**Why it matters:** "Demo patient profile" is internal system language
that means nothing to a real caller, and inserting it unconditionally
(even after being told "no") derails callers who have already stated a
clear, specific need.

**Expected behaviour:** Skip or briefly explain the step only when
actually needed, and stop pushing it once a caller has explicitly
declined.

---

## 5. Provider name changes within a single call

**Severity: MEDIUM.** The same doctor is referred to by different, clearly
garbled names within one continuous conversation:

- S01: "Abreker" → "Abreco" → "Abricker" (turns 17, 19, 21)
- S03: "Zidmio Lukaske" → "Zetmio Lukowski" → "Zbigniew Lacoste" (turn 20 onward)
- S04: "Dougie Houser" → "Dutti Hauser" (turns 18, 20) — same appointment slot
- S07: "Zdmyu Lukovsky" → "Zbigniew Lukaske" (turns 10, 12)

**Why it matters:** A caller confirming who they'll be seeing has no
reliable way to know which name is correct — this reads as the same
underlying fact being regenerated differently each time it's mentioned,
not looked up once and reused.

**Where to look:** `data/runs/run_20260903_065014/`, `.../run_20260903_071722/`,
`.../run_20260903_072507/`, `.../run_20260903_085130/`.

---

## 6. Appointment state gets lost, invented, or both

**Severity: HIGH.** Several calls show the agent either losing track of a
real appointment or fabricating one that was never made:

- **S01** (turn 9): presents an appointment as already booked without ever
  running a booking exchange.
- **S03** (turns 14, 24): fails to locate the caller's stated existing
  Tuesday appointment at all ("I don't see any upcoming appointments"),
  books a new Friday one instead, and never confirms cancelling the
  original — a likely orphaned duplicate.
- **S13** (turn 21): invents a Thursday appointment the caller never
  established in this call, then uses it to block the caller's actual
  request ("I can't book another office visit of the same type right
  now").

**Why it matters:** Whichever direction it goes — losing a real booking or
inventing a fake one — a real patient ends up with an incorrect calendar,
and in S03's case, a real risk of double-booking or a lost appointment
slot.

**Where to look:** `data/runs/run_20260903_065014/`, `.../run_20260903_071722/`,
`.../run_20260903_084150/`.

---

## 7. Dead-end transfers and unresolved endings

**Severity: HIGH.** Three calls end without actually resolving the
caller's final request:

- **S02** (turn 17): agreeing to transfer for a refill question connects
  to a generic message — *"Hello. You've reached the Pretty Good AI test
  line. Goodbye."* — not a real handoff.
- **S04** (turn 24): same generic dead-end, this time when the caller
  asked to be transferred for actual office hours.
- **S07**: the call disconnects immediately after the caller asks for a
  cancellation confirmation email, with no agent response at all — no
  "policy limit" wind-down this time, suggesting the agent's own system
  ended the call mid-request rather than our test harness.

**Why it matters:** "Transfer" appears to be a scripted phrase without a
working handoff behind it, and at least one call simply drops the caller
without answering their last question.

**Where to look:** `data/runs/run_20260903_070441/`, `.../run_20260903_072507/`,
`.../run_20260903_085130/`.

---

## Positive observations

Worth recording, not just bugs: the agent in **S07** correctly respected a
caller's explicit "I'm not ready to rebook right now" without any pressure
to reconsider — one of the better behaviors seen across the batch. **S04**
also correctly declined to book a caller into a closed Sunday slot rather
than blindly confirming it (unlike the failure mode in the assessment
brief's own example bug).

---

## Per-scenario appendix

| Scenario | Call | Turns | Simulator quality | Agent quality | Verified findings |
|---|---|---|---|---|---|
| S01 — New patient booking | `run_20260903_065014` | 22 | 85/100 | 92.2/100 | 4 |
| S02 — Prescription refill | `run_20260903_070441` | 19 | 100/100 | 95.3/100 | 3 |
| S03 — Reschedule, narrow window | `run_20260903_071722` | 26 | 85/100 | 91.3/100 | 3 |
| S04 — Weekend appointment | `run_20260903_072507` | 26 | 85/100 | 94.1/100 | 3 |
| S05 — Insurance coverage | `run_20260903_080225` | 18 | 85/100 | 93.9/100 | 3 |
| S06 — Same-day urgency | `run_20260903_083550` | 17 | 100/100 | 86.5/100 | 4 |
| S07 — Cancellation, refusal to rebook | `run_20260903_085130` | 20 | 100/100 | 94.3/100 | 3 |
| S09 — Interruption / barge-in stress | `run_20260903_081915` | 27 | 100/100 | 100.0/100 | 3 |
| S13 — Contradictory information | `run_20260903_084150` | 27 | 85/100 | 96.3/100 | 2 |
| S14 — Ambiguous opening request | `run_20260903_083003` | 14 | 100/100 | 95.0/100 | 2 |

Each call's full per-finding detail (evidence quote, adjudicator confidence,
verification status) is in `data/runs/<run_id>/bug_report.md`.

## Note on methodology

`ground_truth.yaml` was not populated with the practice's actual office
hours, insurance list, or policies for this submission, so several
factual claims (e.g. "we accept most major insurance plans") could not be
scored — they are quarantined rather than asserted as true or false. The
behavioural findings above (fabricated data, lost/invented appointments,
inconsistent names, unescalated urgency, dead-end transfers) don't depend
on that fact base and are fully verified.

Two calls against S05 and one against S09 are not counted in the totals
above — they were used to diagnose and fix two harness bugs (a dead
ngrok tunnel, and premature turn-taking cutting the agent off mid-sentence)
before a clean re-run. Those runs are still in `data/runs/` as documented
evidence of iteration; see `CONTEXT.md` for the fixes.
