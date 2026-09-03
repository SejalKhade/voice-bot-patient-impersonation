# Bug Report

Run: `run_20260903_073903`  
Generated: 2026-09-03 07:43 UTC  
Calls analysed: 1  
Verified findings: 2  
Withheld findings: 0

## How to read this

Every finding below cites a transcript turn index and quotes the agent verbatim. Findings reached this list only after passing four verification gates: schema and speaker checks, a deterministic verbatim match against the transcript, a fact-dependency check, and independent adjudication sampled several times. Confidence is the adjudicator's mean confidence multiplied by its agreement rate across samples.

Of 2 proposed findings, 0 were withheld from scoring. 0.0% failed verification outright; the remainder were quarantined for depending on a fact about the practice that is not on file. Both kinds are listed below rather than deleted.

---

## Verified findings

### 1. Agent ignored caller's stated status, pushed new-patient flow

**Severity:** HIGH  
**Dimension:** conversational handling  
**Confidence:** 0.73 (100% adjudicator agreement)  
**Call:** `call_01_S05` (scenario S05), turn 4  
**Transcript:** `data/runs/run_20260903_073903/call_01_S05/call_01_S05_transcript.txt`  
**Recording:** `data/recordings/call_01_S05.mp3`

**Agent said:**

> Great. Let's get your demo profile started.

**What happened:** The caller explicitly said twice that she was not a new patient and only wanted to check insurance acceptance, but the agent responded by trying to start a 'demo profile' / new patient intake process, ignoring the stated request entirely.

**Why it matters:** A real caller trying to get a quick yes/no on insurance coverage before booking would be derailed into an irrelevant workflow, wasting time and creating confusion about whether the call is even being handled correctly.

**Expected behaviour:** The agent should have acknowledged the caller's stated intent (checking insurance) and proceeded to address that, rather than initiating an unrelated intake process.

---

### 2. Agent repeated identical incomplete phrase twice in a row

**Severity:** MEDIUM  
**Dimension:** conversational handling  
**Confidence:** 0.95 (100% adjudicator agreement)  
**Call:** `call_01_S05` (scenario S05), turn 20  
**Transcript:** `data/runs/run_20260903_073903/call_01_S05/call_01_S05_transcript.txt`  
**Recording:** `data/recordings/call_01_S05.mp3`

**Agent said:**

> I don't have direct

**What happened:** The agent produced the exact same truncated sentence fragment 'I don't have direct' in two consecutive agent turns (018 and 020), without completing a coherent answer to the caller's repeated question.

**Why it matters:** Looping the same unfinished phrase signals a breakdown in dialogue state tracking, forcing the caller to repeat the same question multiple times before getting any substantive response, which degrades trust and efficiency.

**Expected behaviour:** The agent should have completed its sentence and given a clear, single answer (as it eventually did in turn 024) rather than repeating an unfinished statement.

---

## Withheld findings

_Nothing was withheld in this run._

## Run totals

| Metric | Value |
| --- | --- |
| Calls scored | 1 |
| Mean simulator quality | 100.0 / 100 |
| Mean agent quality | 97.9 / 100 |
| Verified findings | 2 |
| Unverified | 0 |
| Quarantined | 0 |
| Rejected | 0 |
| Candidate filter rate | 0.0% |
