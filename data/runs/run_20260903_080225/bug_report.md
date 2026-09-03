# Bug Report

Run: `run_20260903_080225`  
Generated: 2026-09-03 08:08 UTC  
Calls analysed: 1  
Verified findings: 3  
Withheld findings: 1

## How to read this

Every finding below cites a transcript turn index and quotes the agent verbatim. Findings reached this list only after passing four verification gates: schema and speaker checks, a deterministic verbatim match against the transcript, a fact-dependency check, and independent adjudication sampled several times. Confidence is the adjudicator's mean confidence multiplied by its agreement rate across samples.

Of 4 proposed findings, 1 were withheld from scoring. 25.0% failed verification outright; the remainder were quarantined for depending on a fact about the practice that is not on file. Both kinds are listed below rather than deleted.

---

## Verified findings

### 1. Repeated unhedged coverage claim after being asked to verify

**Severity:** HIGH  
**Dimension:** information accuracy  
**Confidence:** 0.90 (100% adjudicator agreement)  
**Call:** `call_01_S05` (scenario S05), turn 10  
**Transcript:** `data/runs/run_20260903_080225/call_01_S05/call_01_S05_transcript.txt`  
**Recording:** `data/recordings/call_01_S05.mp3`

**Agent said:**

> PivotPoint Orthopedics does accept Blue Cross Blue Shield PPO plans. Can book an appointment using that insurance.

**What happened:** After the caller explicitly asked whether the agent could 'definitively confirm' acceptance or was just going off a general list, the agent again stated the acceptance as a flat fact, only qualifying it two turns later when pressed a third time.

**Why it matters:** Restating an unverifiable claim as definitive fact after being directly asked to clarify its basis undermines trust and could lead the caller to proceed with booking under a false assumption of confirmed coverage.

**Expected behaviour:** When directly asked to distinguish between a verified confirmation and a general list, the agent should have immediately clarified the limitation instead of repeating the unqualified claim.

---

### 2. Irrelevant 'create a demo' response to insurance question

**Severity:** MEDIUM  
**Dimension:** conversational handling  
**Confidence:** 0.95 (100% adjudicator agreement)  
**Call:** `call_01_S05` (scenario S05), turn 2  
**Transcript:** `data/runs/run_20260903_080225/call_01_S05/call_01_S05_transcript.txt`  
**Recording:** `data/recordings/call_01_S05.mp3`

**Agent said:**

> Would you like to create a demo?

**What happened:** The caller stated a clear purpose (confirm insurance before booking), but the agent responded with an unrelated question about creating a 'demo', ignoring the caller's request entirely.

**Why it matters:** This confuses the caller and derails the conversation, forcing them to repeat their request, which could frustrate patients and length the call unnecessarily.

**Expected behaviour:** The agent should have acknowledged the caller's stated intent (insurance verification) and proceeded to address it directly.

---

### 3. Fabricated patient profile and DOB without confirmation

**Severity:** MEDIUM  
**Dimension:** task completion  
**Confidence:** 0.90 (100% adjudicator agreement)  
**Call:** `call_01_S05` (scenario S05), turn 6  
**Transcript:** `data/runs/run_20260903_080225/call_01_S05/call_01_S05_transcript.txt`  
**Recording:** `data/recordings/call_01_S05.mp3`

**Agent said:**

> Your patient profile has been created, and your date of birth is 07/04/2000. For demo purposes.

**What happened:** The agent created a patient profile and populated it with a date of birth the caller never provided, then labeled it as being 'for demo purposes' mid-call.

**Why it matters:** Creating a record with fabricated personal data not supplied by the caller could lead to incorrect patient records or confusion, and referencing 'demo purposes' during a live call is disorienting and suggests test/demo logic leaking into a real interaction.

**Expected behaviour:** The agent should only create or update records with information explicitly confirmed by the caller, and should not reference internal demo/test scaffolding during the call.

---

## Withheld findings

These were proposed by the analyst but did not clear verification. They are listed for completeness and they contributed nothing to any score.

- **Stated insurance acceptance as fact without hedge** (high, `call_01_S05` turn 6) — unverified: Adjudicator majority was INSUFFICIENT. Reported for the reviewer's attention but contributes nothing to the score.

## Run totals

| Metric | Value |
| --- | --- |
| Calls scored | 1 |
| Mean simulator quality | 85.0 / 100 |
| Mean agent quality | 93.9 / 100 |
| Verified findings | 3 |
| Unverified | 1 |
| Quarantined | 0 |
| Rejected | 0 |
| Candidate filter rate | 25.0% |
