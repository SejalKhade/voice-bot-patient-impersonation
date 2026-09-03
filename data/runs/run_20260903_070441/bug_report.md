# Bug Report

Run: `run_20260903_070441`  
Generated: 2026-09-03 07:07 UTC  
Calls analysed: 1  
Verified findings: 3  
Withheld findings: 1

## How to read this

Every finding below cites a transcript turn index and quotes the agent verbatim. Findings reached this list only after passing four verification gates: schema and speaker checks, a deterministic verbatim match against the transcript, a fact-dependency check, and independent adjudication sampled several times. Confidence is the adjudicator's mean confidence multiplied by its agreement rate across samples.

Of 4 proposed findings, 1 were withheld from scoring. 25.0% failed verification outright; the remainder were quarantined for depending on a fact about the practice that is not on file. Both kinds are listed below rather than deleted.

---

## Verified findings

### 1. Agent recorded incorrect date of birth

**Severity:** HIGH  
**Dimension:** information accuracy  
**Confidence:** 0.90 (100% adjudicator agreement)  
**Call:** `call_01_S02` (scenario S02), turn 11  
**Transcript:** `data/runs/run_20260903_070441/call_01_S02/call_01_S02_transcript.txt`  
**Recording:** `data/recordings/call_01_S02.mp3`

**Agent said:**

> Your patient profile is set up, and your date of birth is 07/04/2000.

**What happened:** The patient stated his date of birth as March 15, 1968 twice (turns 002 and 006), but the agent recorded and repeated back a completely different date, 07/04/2000.

**Why it matters:** Incorrect identity data on a medication request could lead to a refill being logged against the wrong patient record or being rejected, delaying care for a blood pressure medication.

**Expected behaviour:** The agent should have accurately captured and confirmed the DOB the patient provided, and corrected it when the patient flagged the error.

---

### 2. Call ended abruptly without resolving transfer

**Severity:** HIGH  
**Dimension:** scope and handoff  
**Confidence:** 0.82 (100% adjudicator agreement)  
**Call:** `call_01_S02` (scenario S02), turn 17  
**Transcript:** `data/runs/run_20260903_070441/call_01_S02/call_01_S02_transcript.txt`  
**Recording:** `data/recordings/call_01_S02.mp3`

**Agent said:**

> Hello. You've reached the Pretty Good AI test line. Goodbye.

**What happened:** After the patient agreed to be transferred to a human for help with the refill, the agent's transfer resulted in a generic disconnection message ('test line... Goodbye') instead of connecting the patient to support, leaving the request unresolved.

**Why it matters:** The patient's request for a refill and pharmacy information was never actually handed off to a human, meaning the escalation failed and the patient had to restate everything.

**Expected behaviour:** The agent should have successfully transferred the call to a human agent who could complete the refill request, or clearly informed the patient that the transfer failed and offered an alternative.

---

### 3. Agent referenced internal 'demo' profile to patient

**Severity:** LOW  
**Dimension:** conversational handling  
**Confidence:** 0.95 (100% adjudicator agreement)  
**Call:** `call_01_S02` (scenario S02), turn 7  
**Transcript:** `data/runs/run_20260903_070441/call_01_S02/call_01_S02_transcript.txt`  
**Recording:** `data/recordings/call_01_S02.mp3`

**Agent said:**

> Let me finish setting up your demo patient profile. That'll help with your lisinopril refill. One moment.

**What happened:** The agent referred to the patient's profile as a 'demo patient profile' while speaking directly to the patient, exposing internal/test terminology in a live interaction.

**Why it matters:** This undermines patient confidence that their information is being handled correctly and suggests the agent may be treating the interaction as non-authoritative.

**Expected behaviour:** The agent should use patient-facing language only, avoiding internal system labels like 'demo' when addressing the caller.

---

## Withheld findings

These were proposed by the analyst but did not clear verification. They are listed for completeness and they contributed nothing to any score.

- **Refill request never logged despite drug/dose given** (high, `call_01_S02` turn 13) — unverified: Adjudicator majority was NOT_SUPPORTED. Reported for the reviewer's attention but contributes nothing to the score.

## Run totals

| Metric | Value |
| --- | --- |
| Calls scored | 1 |
| Mean simulator quality | 100.0 / 100 |
| Mean agent quality | 95.3 / 100 |
| Verified findings | 3 |
| Unverified | 1 |
| Quarantined | 0 |
| Rejected | 0 |
| Candidate filter rate | 25.0% |
