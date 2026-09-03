# Bug Report

Run: `run_20260903_083003`  
Generated: 2026-09-03 08:33 UTC  
Calls analysed: 1  
Verified findings: 2  
Withheld findings: 1

## How to read this

Every finding below cites a transcript turn index and quotes the agent verbatim. Findings reached this list only after passing four verification gates: schema and speaker checks, a deterministic verbatim match against the transcript, a fact-dependency check, and independent adjudication sampled several times. Confidence is the adjudicator's mean confidence multiplied by its agreement rate across samples.

Of 3 proposed findings, 1 were withheld from scoring. 33.3% failed verification outright; the remainder were quarantined for depending on a fact about the practice that is not on file. Both kinds are listed below rather than deleted.

---

## Verified findings

### 1. Ignored ambiguous request, offered unrelated demo profile

**Severity:** HIGH  
**Dimension:** conversational handling  
**Confidence:** 0.90 (100% adjudicator agreement)  
**Call:** `call_01_S14` (scenario S14), turn 2  
**Transcript:** `data/runs/run_20260903_083003/call_01_S14/call_01_S14_transcript.txt`  
**Recording:** `data/recordings/call_01_S14.mp3`

**Agent said:**

> Before we continue, would you like to create a demo patient profile? I just need your first and last name.

**What happened:** The caller opened with a vague reference to 'the thing from last time' but the agent did not ask what that referred to. Instead it pivoted to an unrelated offer to create a 'demo patient profile', which the caller had not requested.

**Why it matters:** A real caller would be confused and delayed in reaching the right process; the agent failed to establish the actual reason for the call before proceeding, which could lead to mishandled requests.

**Expected behaviour:** The agent should have asked a clarifying question such as 'Can you tell me more about what you're following up on?' rather than introducing an unrelated demo-profile offer.

---

### 2. Fabricated caller's date of birth

**Severity:** HIGH  
**Dimension:** information accuracy  
**Confidence:** 0.90 (100% adjudicator agreement)  
**Call:** `call_01_S14` (scenario S14), turn 4  
**Transcript:** `data/runs/run_20260903_083003/call_01_S14/call_01_S14_transcript.txt`  
**Recording:** `data/recordings/call_01_S14.mp3`

**Agent said:**

> Your patient profile is set up, and your date of birth is 07/04/2000 for demo purposes.

**What happened:** The agent stated a specific date of birth for the caller that the caller never provided, presenting it as an established fact tied to the patient's profile.

**Why it matters:** Inventing identifying details like date of birth risks corrupting patient records or creating false identity associations, which is a serious accuracy and safety concern in a medical context.

**Expected behaviour:** The agent should not state or record any date of birth unless the caller actually provided it, and should ask for it directly if needed for identification.

---

## Withheld findings

These were proposed by the analyst but did not clear verification. They are listed for completeness and they contributed nothing to any score.

- **No concrete follow-up plan for records request** (medium, `call_01_S14` turn 10) — unverified: Adjudicator majority was NOT_SUPPORTED. Reported for the reviewer's attention but contributes nothing to the score.

## Run totals

| Metric | Value |
| --- | --- |
| Calls scored | 1 |
| Mean simulator quality | 100.0 / 100 |
| Mean agent quality | 95.0 / 100 |
| Verified findings | 2 |
| Unverified | 1 |
| Quarantined | 0 |
| Rejected | 0 |
| Candidate filter rate | 33.3% |
