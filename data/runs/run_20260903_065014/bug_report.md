# Bug Report

Run: `run_20260903_065014`  
Generated: 2026-09-03 06:55 UTC  
Calls analysed: 1  
Verified findings: 4  
Withheld findings: 1

## How to read this

Every finding below cites a transcript turn index and quotes the agent verbatim. Findings reached this list only after passing four verification gates: schema and speaker checks, a deterministic verbatim match against the transcript, a fact-dependency check, and independent adjudication sampled several times. Confidence is the adjudicator's mean confidence multiplied by its agreement rate across samples.

Of 5 proposed findings, 1 were withheld from scoring. 20.0% failed verification outright; the remainder were quarantined for depending on a fact about the practice that is not on file. Both kinds are listed below rather than deleted.

---

## Verified findings

### 1. Agent invented date of birth without asking caller

**Severity:** HIGH  
**Dimension:** information accuracy  
**Confidence:** 0.90 (100% adjudicator agreement)  
**Call:** `call_01_S01` (scenario S01), turn 5  
**Transcript:** `data/runs/run_20260903_065014/call_01_S01/call_01_S01_transcript.txt`  
**Recording:** `data/recordings/call_01_S01.mp3`

**Agent said:**

> Your patient profile is set up, and your date of birth is 07/04/2000 for demo purposes.

**What happened:** The agent stated a specific date of birth for the caller without ever having asked the caller for it, then labelled it 'for demo purposes'.

**Why it matters:** Fabricating identity details rather than collecting them from the patient undermines proper patient identification, which is essential for medical scheduling and record accuracy.

**Expected behaviour:** The agent should have asked the caller to provide their date of birth rather than asserting a fabricated value.

---

### 2. Appointment presented as pre-existing without a booking exchange

**Severity:** HIGH  
**Dimension:** task completion  
**Confidence:** 0.77 (100% adjudicator agreement)  
**Call:** `call_01_S01` (scenario S01), turn 9  
**Transcript:** `data/runs/run_20260903_065014/call_01_S01/call_01_S01_transcript.txt`  
**Recording:** `data/recordings/call_01_S01.mp3`

**Agent said:**

> You already have a new patient appointment booked for Thursday September 3 at 9AM. Would you like to keep this appointment

**What happened:** Instead of offering concrete available date/time options in response to the caller's request for a weekday morning slot, the agent asserted that an appointment was 'already' booked, with no visible process establishing when or how it was scheduled.

**Why it matters:** A patient cannot be confident a real, deliberate booking occurred if the agent presents it as a fait accompli rather than walking through available times and confirming a selection.

**Expected behaviour:** The agent should have offered specific available weekday morning slots and let the caller choose one, then confirmed the choice explicitly.

---

### 3. Ignored caller's correction of date of birth

**Severity:** MEDIUM  
**Dimension:** conversational handling  
**Confidence:** 0.81 (100% adjudicator agreement)  
**Call:** `call_01_S01` (scenario S01), turn 7  
**Transcript:** `data/runs/run_20260903_065014/call_01_S01/call_01_S01_transcript.txt`  
**Recording:** `data/recordings/call_01_S01.mp3`

**Agent said:**

> Do you have a specific doctor in mind, or would you like to see the first available provider?

**What happened:** Immediately after the caller corrected the fabricated date of birth to 1990, the agent moved on to a new topic without acknowledging or confirming the correction.

**Why it matters:** Failing to confirm a corrected identifier risks the wrong date of birth remaining on file, causing identification problems for the patient's medical record.

**Expected behaviour:** The agent should have acknowledged and confirmed the corrected date of birth before proceeding.

---

### 4. Provider name inconsistent across turns

**Severity:** LOW  
**Dimension:** conversational handling  
**Confidence:** 0.78 (100% adjudicator agreement)  
**Call:** `call_01_S01` (scenario S01), turn 21  
**Transcript:** `data/runs/run_20260903_065014/call_01_S01/call_01_S01_transcript.txt`  
**Recording:** `data/recordings/call_01_S01.mp3`

**Agent said:**

> Your appointment for Thursday, September 3 with Abricker has been canceled.

**What happened:** The provider's name was rendered differently across consecutive turns: 'Abreker' (turn 17), 'Abreco' (turn 19), and 'Abricker' (turn 21), all referring to the same appointment.

**Why it matters:** Inconsistent naming of the same entity within one call signals unstable state tracking and could confuse a patient trying to confirm who they were scheduled with.

**Expected behaviour:** The agent should have used a single, consistent provider name throughout the call.

---

## Withheld findings

These were proposed by the analyst but did not clear verification. They are listed for completeness and they contributed nothing to any score.

- **Practice specialty mismatch not surfaced before booking** (high, `call_01_S01` turn 13) — unverified: Supported but unstable: 0.53 falls below the 0.55 threshold. Contributes nothing to the score.

## Run totals

| Metric | Value |
| --- | --- |
| Calls scored | 1 |
| Mean simulator quality | 85.0 / 100 |
| Mean agent quality | 92.2 / 100 |
| Verified findings | 4 |
| Unverified | 1 |
| Quarantined | 0 |
| Rejected | 0 |
| Candidate filter rate | 20.0% |
