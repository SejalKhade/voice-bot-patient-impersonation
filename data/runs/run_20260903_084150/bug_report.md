# Bug Report

Run: `run_20260903_084150`  
Generated: 2026-09-03 08:47 UTC  
Calls analysed: 1  
Verified findings: 2  
Withheld findings: 1

## How to read this

Every finding below cites a transcript turn index and quotes the agent verbatim. Findings reached this list only after passing four verification gates: schema and speaker checks, a deterministic verbatim match against the transcript, a fact-dependency check, and independent adjudication sampled several times. Confidence is the adjudicator's mean confidence multiplied by its agreement rate across samples.

Of 3 proposed findings, 1 were withheld from scoring. 33.3% failed verification outright; the remainder were quarantined for depending on a fact about the practice that is not on file. Both kinds are listed below rather than deleted.

---

## Verified findings

### 1. Fabricates an appointment never established in the call

**Severity:** HIGH  
**Dimension:** information accuracy  
**Confidence:** 0.78 (100% adjudicator agreement)  
**Call:** `call_01_S13` (scenario S13), turn 21  
**Transcript:** `data/runs/run_20260903_084150/call_01_S13/call_01_S13_transcript.txt`  
**Recording:** `data/recordings/call_01_S13.mp3`

**Agent said:**

> You have an office visit already scheduled for Thursday, September 10 at 2PM. Because of this, I can't book another office visit of the same type right now. Would you like to reschedule your current appointment to Wednesday instead?

**What happened:** The agent asserted the caller already had a scheduled office visit for Thursday, September 10 at 2PM, a detail that never appeared anywhere earlier in the conversation, and which the caller explicitly denied ('No, I don't have anything scheduled yet').

**Why it matters:** Presenting a fabricated or contradicted fact as established truth could block a real booking, confuse the patient about their own records, and erode trust in the system's accuracy.

**Expected behaviour:** The agent should not have introduced an appointment that was never mentioned or confirmed, and should have accepted the caller's correction that no appointment existed, or checked the actual record and reported honestly if uncertain.

---

### 2. Introduces confusing 'demo patient profile' jargon

**Severity:** MEDIUM  
**Dimension:** conversational handling  
**Confidence:** 0.85 (100% adjudicator agreement)  
**Call:** `call_01_S13` (scenario S13), turn 6  
**Transcript:** `data/runs/run_20260903_084150/call_01_S13/call_01_S13_transcript.txt`  
**Recording:** `data/recordings/call_01_S13.mp3`

**Agent said:**

> to help you book an appointment. I'll need to create a demo patient profile for you Can I have your first and last name?

**What happened:** The agent introduced an undefined term ('demo patient profile') that the caller had already flagged as confusing in the prior turn, without ever explaining what it meant.

**Why it matters:** Unexplained internal/system terminology can make a real patient worried their information is being handled incorrectly or that they are being enrolled in something unintended.

**Expected behaviour:** The agent should have simply proceeded to collect the caller's name to book the appointment without referencing internal system labels like 'demo' profile.

---

## Withheld findings

These were proposed by the analyst but did not clear verification. They are listed for completeness and they contributed nothing to any score.

- **Call ends without a confirmed appointment or time offered** (high, `call_01_S13` turn 23) — unverified: Supported but unstable: 0.55 falls below the 0.55 threshold. Contributes nothing to the score.

## Run totals

| Metric | Value |
| --- | --- |
| Calls scored | 1 |
| Mean simulator quality | 85.0 / 100 |
| Mean agent quality | 96.3 / 100 |
| Verified findings | 2 |
| Unverified | 1 |
| Quarantined | 0 |
| Rejected | 0 |
| Candidate filter rate | 33.3% |
