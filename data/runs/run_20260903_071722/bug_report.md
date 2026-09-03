# Bug Report

Run: `run_20260903_071722`  
Generated: 2026-09-03 07:23 UTC  
Calls analysed: 1  
Verified findings: 3  
Withheld findings: 2

## How to read this

Every finding below cites a transcript turn index and quotes the agent verbatim. Findings reached this list only after passing four verification gates: schema and speaker checks, a deterministic verbatim match against the transcript, a fact-dependency check, and independent adjudication sampled several times. Confidence is the adjudicator's mean confidence multiplied by its agreement rate across samples.

Of 5 proposed findings, 2 were withheld from scoring. 40.0% failed verification outright; the remainder were quarantined for depending on a fact about the practice that is not on file. Both kinds are listed below rather than deleted.

---

## Verified findings

### 1. Agent invents a date of birth never provided

**Severity:** HIGH  
**Dimension:** information accuracy  
**Confidence:** 0.95 (100% adjudicator agreement)  
**Call:** `call_01_S03` (scenario S03), turn 12  
**Transcript:** `data/runs/run_20260903_071722/call_01_S03/call_01_S03_transcript.txt`  
**Recording:** `data/recordings/call_01_S03.mp3`

**Agent said:**

> Your patient profile is set up. And your date of birth is 07/04/2000. How can I help you today?

**What happened:** The agent states a specific date of birth for the caller that was never given in the conversation, and the caller immediately confirms it is wrong.

**Why it matters:** Fabricating identifying patient information is a serious data-integrity failure that could lead to matching the wrong patient record or corrupting the correct one.

**Expected behaviour:** The agent should never assert patient identifying details that were not supplied; it should ask the caller to provide or confirm date of birth.

---

### 2. Agent fails to locate confirmed existing appointment

**Severity:** HIGH  
**Dimension:** task completion  
**Confidence:** 0.82 (100% adjudicator agreement)  
**Call:** `call_01_S03` (scenario S03), turn 14  
**Transcript:** `data/runs/run_20260903_071722/call_01_S03/call_01_S03_transcript.txt`  
**Recording:** `data/recordings/call_01_S03.mp3`

**Agent said:**

> I don't see any upcoming appointments for you on the system. Would you like me to help you book a new appointment for Thursday or Friday after 3PM?

**What happened:** The caller clearly stated an existing Tuesday 2pm appointment with a confirmation received, but the agent reports no record and pivots to booking a new appointment without further identity verification attempts (e.g., asking for phone number, confirmation number, or correct DOB).

**Why it matters:** If the original appointment is not actually cancelled, the patient may end up double-booked or the old appointment may go unaddressed, causing confusion or a missed/duplicate visit.

**Expected behaviour:** The agent should have asked for additional identifying information (correct DOB, phone number, confirmation number) before concluding the appointment does not exist, and should have addressed the fate of the original Tuesday appointment explicitly.

---

### 3. Doctor's name changes across three consecutive turns

**Severity:** MEDIUM  
**Dimension:** information accuracy  
**Confidence:** 0.85 (100% adjudicator agreement)  
**Call:** `call_01_S03` (scenario S03), turn 24  
**Transcript:** `data/runs/run_20260903_071722/call_01_S03/call_01_S03_transcript.txt`  
**Recording:** `data/recordings/call_01_S03.mp3`

**Agent said:**

> Your appointment is confirmed for Friday, September 4 at 03:30PM with doctor Zbigniew Lacoste at Pivot Point Orthopaedics.

**What happened:** The agent refers to the provider as 'doctor Zidmio Lukaske' in turn 020, 'doctor Zetmio Lukowski' in turn 022, and 'doctor Zbigniew Lacoste' in the final confirmation in turn 024 — three different names for what should be the same provider.

**Why it matters:** Inconsistent provider identification in a booking confirmation could cause the patient to arrive expecting the wrong doctor or doubt the reliability of the confirmation altogether.

**Expected behaviour:** The agent should consistently state the same, correct provider name throughout the call and in the final confirmation.

---

## Withheld findings

These were proposed by the analyst but did not clear verification. They are listed for completeness and they contributed nothing to any score.

- **Agent diverts to demo profile instead of reschedule** (medium, `call_01_S03` turn 10) — unverified: Supported but unstable: 0.48 falls below the 0.55 threshold. Contributes nothing to the score.
- **Old Tuesday appointment cancellation never confirmed** (high, `call_01_S03` turn 24) — unverified: Adjudicator majority was INSUFFICIENT. Reported for the reviewer's attention but contributes nothing to the score.

## Run totals

| Metric | Value |
| --- | --- |
| Calls scored | 1 |
| Mean simulator quality | 85.0 / 100 |
| Mean agent quality | 91.3 / 100 |
| Verified findings | 3 |
| Unverified | 2 |
| Quarantined | 0 |
| Rejected | 0 |
| Candidate filter rate | 40.0% |
