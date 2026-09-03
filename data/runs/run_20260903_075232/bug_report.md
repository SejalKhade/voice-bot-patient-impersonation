# Bug Report

Run: `run_20260903_075232`  
Generated: 2026-09-03 07:56 UTC  
Calls analysed: 1  
Verified findings: 2  
Withheld findings: 2

## How to read this

Every finding below cites a transcript turn index and quotes the agent verbatim. Findings reached this list only after passing four verification gates: schema and speaker checks, a deterministic verbatim match against the transcript, a fact-dependency check, and independent adjudication sampled several times. Confidence is the adjudicator's mean confidence multiplied by its agreement rate across samples.

Of 4 proposed findings, 2 were withheld from scoring. 50.0% failed verification outright; the remainder were quarantined for depending on a fact about the practice that is not on file. Both kinds are listed below rather than deleted.

---

## Verified findings

### 1. Agent offers irrelevant demo profile instead of answering

**Severity:** HIGH  
**Dimension:** task completion  
**Confidence:** 0.97 (100% adjudicator agreement)  
**Call:** `call_01_S05` (scenario S05), turn 2  
**Transcript:** `data/runs/run_20260903_075232/call_01_S05/call_01_S05_transcript.txt`  
**Recording:** `data/recordings/call_01_S05.mp3`

**Agent said:**

> Would you like to create a demo patient profile?

**What happened:** The patient asked directly whether the practice accepts Blue Cross Blue Shield PPO insurance, but the agent responded with an unrelated offer to create a demo patient profile.

**Why it matters:** The caller's core question is ignored from the very first response, delaying resolution of a real insurance verification need.

**Expected behaviour:** The agent should have addressed the insurance question directly, either confirming, denying, or stating it needs to verify.

---

### 2. Agent repeats demo prompt after explicit correction

**Severity:** HIGH  
**Dimension:** conversational handling  
**Confidence:** 0.95 (100% adjudicator agreement)  
**Call:** `call_01_S05` (scenario S05), turn 4  
**Transcript:** `data/runs/run_20260903_075232/call_01_S05/call_01_S05_transcript.txt`  
**Recording:** `data/recordings/call_01_S05.mp3`

**Agent said:**

> Great. Let's get your demo patient.

**What happened:** After the patient explicitly said they were not looking for a demo profile and restated their insurance question, the agent again pushed forward with the demo patient flow.

**Why it matters:** Ignoring an explicit correction shows the agent is not tracking conversation state, frustrating the caller and stalling the interaction.

**Expected behaviour:** The agent should have acknowledged the correction and moved to address the insurance question instead of repeating the same irrelevant prompt.

---

## Withheld findings

These were proposed by the analyst but did not clear verification. They are listed for completeness and they contributed nothing to any score.

- **Agent produces repeated incomplete/truncated responses** (medium, `call_01_S05` turn 6) — unverified: Adjudicator majority was INSUFFICIENT. Reported for the reviewer's attention but contributes nothing to the score.
- **No transfer or callback offered when explicitly requested** (high, `call_01_S05` turn 22) — unverified: Adjudicator majority was INSUFFICIENT. Reported for the reviewer's attention but contributes nothing to the score.

## Run totals

| Metric | Value |
| --- | --- |
| Calls scored | 1 |
| Mean simulator quality | 100.0 / 100 |
| Mean agent quality | 93.9 / 100 |
| Verified findings | 2 |
| Unverified | 2 |
| Quarantined | 0 |
| Rejected | 0 |
| Candidate filter rate | 50.0% |
