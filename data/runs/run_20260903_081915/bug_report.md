# Bug Report

Run: `run_20260903_081915`  
Generated: 2026-09-03 08:28 UTC  
Calls analysed: 1  
Verified findings: 3  
Withheld findings: 0

## How to read this

Every finding below cites a transcript turn index and quotes the agent verbatim. Findings reached this list only after passing four verification gates: schema and speaker checks, a deterministic verbatim match against the transcript, a fact-dependency check, and independent adjudication sampled several times. Confidence is the adjudicator's mean confidence multiplied by its agreement rate across samples.

Of 3 proposed findings, 0 were withheld from scoring. 0.0% failed verification outright; the remainder were quarantined for depending on a fact about the practice that is not on file. Both kinds are listed below rather than deleted.

---

## Verified findings

### 1. Agent invents a date of birth the caller never provided

**Severity:** HIGH  
**Dimension:** information accuracy  
**Confidence:** 0.87 (100% adjudicator agreement)  
**Call:** `call_01_S09` (scenario S09), turn 9  
**Transcript:** `data/runs/run_20260903_081915/call_01_S09/call_01_S09_transcript.txt`  
**Recording:** `data/recordings/call_01_S09.mp3`

**Agent said:**

> Your patient profile is set up. And your date of birth is 07/04/2000 for demo purposes. How can I help you today?

**What happened:** The agent stated a specific date of birth (07/04/2000) as though it were the caller's real recorded information, but the caller had never supplied a date of birth at any point in the conversation.

**Why it matters:** In a medical context, presenting fabricated identity data as fact risks corrupting patient records, causing identity mismatches, or misleading the patient about what information is on file, which can have downstream clinical and administrative consequences.

**Expected behaviour:** The agent should have asked the caller for their date of birth rather than asserting an invented value, or clearly flagged that the value was a placeholder before treating it as confirmed patient data.

---

### 2. Agent repeats acknowledgment without progressing after barge-ins

**Severity:** MEDIUM  
**Dimension:** conversational handling  
**Confidence:** 0.78 (100% adjudicator agreement)  
**Call:** `call_01_S09` (scenario S09), turn 6  
**Transcript:** `data/runs/run_20260903_081915/call_01_S09/call_01_S09_transcript.txt`  
**Recording:** `data/recordings/call_01_S09.mp3`

**Agent said:**

> no problem. I'll help you with a Thursday afternoon appoint.

**What happened:** After being interrupted twice, the agent produced two more short acknowledgment fragments (turns 004, 006) that restated the same 'I'll help with Thursday afternoon' idea instead of moving directly to the next required step, before finally asking for the name in turn 007.

**Why it matters:** Repeated re-acknowledgment without advancing the task wastes the caller's time and can feel like the agent is stuck in a loop, which is frustrating for a caller who has already repeated their request twice.

**Expected behaviour:** After confirming it understood the Thursday afternoon request once, the agent should have moved straight to the next necessary step (e.g., asking for the name) rather than re-stating the same acknowledgment across multiple turns.

---

### 3. Agent mid-sentence restart while stating existing appointment

**Severity:** LOW  
**Dimension:** conversational handling  
**Confidence:** 0.90 (100% adjudicator agreement)  
**Call:** `call_01_S09` (scenario S09), turn 13  
**Transcript:** `data/runs/run_20260903_081915/call_01_S09/call_01_S09_transcript.txt`  
**Recording:** `data/recordings/call_01_S09.mp3`

**Agent said:**

> You already have an office visit booked for Friday, September yeah. The office visit's already scheduled for Friday, September 4 at 03:30PM.

**What happened:** The agent began a sentence, cut itself off mid-word, and restarted the same sentence again without any interruption from the caller.

**Why it matters:** Even without caller interruption, self-restarting sentences suggests unstable turn/state tracking and can confuse the caller about what information is being conveyed, especially for appointment details.

**Expected behaviour:** The agent should deliver the appointment detail in a single coherent sentence without restarting mid-way.

---

## Withheld findings

_Nothing was withheld in this run._

## Run totals

| Metric | Value |
| --- | --- |
| Calls scored | 1 |
| Mean simulator quality | 100.0 / 100 |
| Mean agent quality | 95.8 / 100 |
| Verified findings | 3 |
| Unverified | 0 |
| Quarantined | 0 |
| Rejected | 0 |
| Candidate filter rate | 0.0% |
