# Bug Report

Run: `run_20260903_063047`  
Generated: 2026-09-03 06:36 UTC  
Calls analysed: 1  
Verified findings: 1  
Withheld findings: 3

## How to read this

Every finding below cites a transcript turn index and quotes the agent verbatim. Findings reached this list only after passing four verification gates: schema and speaker checks, a deterministic verbatim match against the transcript, a fact-dependency check, and independent adjudication sampled several times. Confidence is the adjudicator's mean confidence multiplied by its agreement rate across samples.

Of 4 proposed findings, 3 were withheld from scoring. 75.0% failed verification outright; the remainder were quarantined for depending on a fact about the practice that is not on file. Both kinds are listed below rather than deleted.

---

## Verified findings

### 1. Garbled, nonsensical agent utterance

**Severity:** MEDIUM  
**Dimension:** conversational handling  
**Confidence:** 0.90 (100% adjudicator agreement)  
**Call:** `call_01_S01` (scenario S01), turn 25  
**Transcript:** `data/runs/run_20260903_063047/call_01_S01/call_01_S01_transcript.txt`  
**Recording:** `data/recordings/call_01_S01.mp3`

**Agent said:**

> You're skid.

**What happened:** The agent produced an incoherent phrase that does not correspond to any meaningful response to the caller's question about appointment details and what to bring.

**Why it matters:** Incoherent output degrades trust in the system and forces the caller to repeatedly ask for clarification, extending call length and causing confusion about appointment status.

**Expected behaviour:** The agent should have produced a clear, complete sentence addressing the caller's question, or explicitly asked the caller to hold if there was a system issue.

---

## Withheld findings

These were proposed by the analyst but did not clear verification. They are listed for completeness and they contributed nothing to any score.

- **Appointment confirmation cut off, never completed** (high, `call_01_S01` turn 27) — unverified: Adjudicator majority was NOT_SUPPORTED. Reported for the reviewer's attention but contributes nothing to the score.
- **Offered weekend slot after caller specified weekday mornings only** (high, `call_01_S01` turn 23) — unverified: Adjudicator majority was INSUFFICIENT. Reported for the reviewer's attention but contributes nothing to the score.
- **New-patient paperwork question never answered** (high, `call_01_S01` turn 27) — unverified: Adjudicator majority was INSUFFICIENT. Reported for the reviewer's attention but contributes nothing to the score.

## Run totals

| Metric | Value |
| --- | --- |
| Calls scored | 1 |
| Mean simulator quality | 100.0 / 100 |
| Mean agent quality | 99.2 / 100 |
| Verified findings | 1 |
| Unverified | 3 |
| Quarantined | 0 |
| Rejected | 0 |
| Candidate filter rate | 75.0% |
