# Bug Report

Run: `run_20260903_072507`  
Generated: 2026-09-03 07:30 UTC  
Calls analysed: 1  
Verified findings: 3  
Withheld findings: 0

## How to read this

Every finding below cites a transcript turn index and quotes the agent verbatim. Findings reached this list only after passing four verification gates: schema and speaker checks, a deterministic verbatim match against the transcript, a fact-dependency check, and independent adjudication sampled several times. Confidence is the adjudicator's mean confidence multiplied by its agreement rate across samples.

Of 3 proposed findings, 0 were withheld from scoring. 0.0% failed verification outright; the remainder were quarantined for depending on a fact about the practice that is not on file. Both kinds are listed below rather than deleted.

---

## Verified findings

### 1. Agent invented a date of birth caller never gave

**Severity:** HIGH  
**Dimension:** information accuracy  
**Confidence:** 0.90 (100% adjudicator agreement)  
**Call:** `call_01_S04` (scenario S04), turn 10  
**Transcript:** `data/runs/run_20260903_072507/call_01_S04/call_01_S04_transcript.txt`  
**Recording:** `data/recordings/call_01_S04.mp3`

**Agent said:**

> Your patient profile is set up, and your date of birth is 07/04/2000 for demo purposes. How may I help you today?

**What happened:** The agent stated a specific date of birth (07/04/2000) for the caller's profile without ever asking the caller for it, and the caller had not supplied one.

**Why it matters:** Fabricating patient identifying data risks creating an inaccurate medical record, which could lead to mismatched records or downstream clinical/administrative errors.

**Expected behaviour:** The agent should have asked the caller for their date of birth rather than asserting a fabricated value on the profile.

---

### 2. Transfer for office hours led to a dead-end, not a real answer

**Severity:** HIGH  
**Dimension:** scope and handoff  
**Confidence:** 0.77 (100% adjudicator agreement)  
**Call:** `call_01_S04` (scenario S04), turn 24  
**Transcript:** `data/runs/run_20260903_072507/call_01_S04/call_01_S04_transcript.txt`  
**Recording:** `data/recordings/call_01_S04.mp3`

**Agent said:**

> Hello. You've reached the Pretty Good AI test line. Goodbye.

**What happened:** After the caller asked to be transferred to someone who could state the actual office hours, the transfer connected to a generic test-line message and immediately ended the call without providing the requested information or a human contact.

**Why it matters:** The caller's explicit request for office hours was never fulfilled and the call ended abruptly, meaning the core task (getting accurate hours before booking) failed entirely.

**Expected behaviour:** The transfer should route to a person or system able to actually answer the office-hours question, or the agent should have provided a concrete alternative (e.g., a callback, a link, or a promise to follow up) rather than ending the call with an unhelpful message.

---

### 3. Provider name changes for the same appointment slot

**Severity:** MEDIUM  
**Dimension:** information accuracy  
**Confidence:** 0.90 (100% adjudicator agreement)  
**Call:** `call_01_S04` (scenario S04), turn 20  
**Transcript:** `data/runs/run_20260903_072507/call_01_S04/call_01_S04_transcript.txt`  
**Recording:** `data/recordings/call_01_S04.mp3`

**Agent said:**

> Would you like to go ahead and book the 05:15PM slot with Dutti Hauser?

**What happened:** The agent referred to the same Tuesday 5:15PM slot with two different provider names: 'Dougie Houser' in turn 018 and 'Dutti Hauser' in turn 020.

**Why it matters:** Inconsistent provider identification could confuse the patient about who they are actually booked to see, undermining trust and record accuracy.

**Expected behaviour:** The agent should have used a single, consistent provider name for the same appointment slot throughout the call.

---

## Withheld findings

_Nothing was withheld in this run._

## Run totals

| Metric | Value |
| --- | --- |
| Calls scored | 1 |
| Mean simulator quality | 85.0 / 100 |
| Mean agent quality | 94.1 / 100 |
| Verified findings | 3 |
| Unverified | 0 |
| Quarantined | 0 |
| Rejected | 0 |
| Candidate filter rate | 0.0% |
