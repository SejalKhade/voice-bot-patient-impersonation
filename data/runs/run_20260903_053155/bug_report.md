# Bug Report

Run: `run_20260903_053155`  
Generated: 2026-09-03 06:17 UTC  
Calls analysed: 1  
Verified findings: 3  
Withheld findings: 0

## How to read this

Every finding below cites a transcript turn index and quotes the agent verbatim. Findings reached this list only after passing four verification gates: schema and speaker checks, a deterministic verbatim match against the transcript, a fact-dependency check, and independent adjudication sampled several times. Confidence is the adjudicator's mean confidence multiplied by its agreement rate across samples.

Of 3 proposed findings, 0 were withheld from scoring. 0.0% failed verification outright; the remainder were quarantined for depending on a fact about the practice that is not on file. Both kinds are listed below rather than deleted.

---

## Verified findings

### 1. Agent asks to create 'demo patient profile' instead of booking

**Severity:** HIGH  
**Dimension:** task completion  
**Confidence:** 0.90 (100% adjudicator agreement)  
**Call:** `call_01_S01` (scenario S01), turn 1  
**Transcript:** `data/runs/run_20260903_053155/call_01_S01/call_01_S01_transcript.txt`  
**Recording:** `data/recordings/call_01_S01.mp3`

**Agent said:**

> Would you like to create a demo patient profile?

**What happened:** Instead of addressing the caller's request to book a new-patient appointment, the agent asked about creating a 'demo patient profile', which appears to be leaked internal/test language rather than a real booking step.

**Why it matters:** A real caller trying to book an appointment would be confused and unable to proceed, since the agent never attempts to gather appointment-relevant information or offer scheduling.

**Expected behaviour:** The agent should have acknowledged the request to book a new-patient appointment and begun collecting the caller's name, date of birth, and reason for visit.

---

### 2. Call ends with no appointment booked or information confirmed

**Severity:** HIGH  
**Dimension:** task completion  
**Confidence:** 0.85 (100% adjudicator agreement)  
**Call:** `call_01_S01` (scenario S01), turn 5  
**Transcript:** `data/runs/run_20260903_053155/call_01_S01/call_01_S01_transcript.txt`  
**Recording:** `data/recordings/call_01_S01.mp3`

**Agent said:**

> I am going to end the call now. Goodbye.

**What happened:** The agent terminates the call without having collected the caller's name, offered any appointment times, booked anything, or provided any information about new-patient paperwork.

**Why it matters:** The caller's core objective—booking a new-patient appointment and knowing the date/time/what to bring—was completely unmet, leaving the patient without care and needing to call back or seek help elsewhere.

**Expected behaviour:** The agent should have continued attempting to assist, offered concrete appointment slots, and confirmed the booking details, or clearly transferred to a human before ending the call.

---

### 3. Agent repeats identical scripted prompt without progressing

**Severity:** MEDIUM  
**Dimension:** conversational handling  
**Confidence:** 0.57 (67% adjudicator agreement)  
**Call:** `call_01_S01` (scenario S01), turn 3  
**Transcript:** `data/runs/run_20260903_053155/call_01_S01/call_01_S01_transcript.txt`  
**Recording:** `data/recordings/call_01_S01.mp3`

**Agent said:**

> Welcome to PivotPoint Orthopedics. Would you like to create a demo patient profile? I just need your first and last name.

**What happened:** The agent repeated its earlier greeting and question verbatim, with no acknowledgment of anything the caller may have said or any adaptation to the conversation state.

**Why it matters:** Looping the same script signals the agent lost track of the conversation, frustrating the caller and stalling task progress.

**Expected behaviour:** The agent should track that it already asked this question and either move forward with new information or ask a clarifying follow-up rather than repeating itself verbatim.

---

## Withheld findings

_Nothing was withheld in this run._

## Run totals

| Metric | Value |
| --- | --- |
| Calls scored | 1 |
| Mean simulator quality | 25.0 / 100 |
| Mean agent quality | 91.6 / 100 |
| Verified findings | 3 |
| Unverified | 0 |
| Quarantined | 0 |
| Rejected | 0 |
| Candidate filter rate | 0.0% |
