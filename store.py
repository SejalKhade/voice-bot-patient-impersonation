"""
Persistence and report generation.

Runs are plain JSON on disk. No database, because the deliverable is a
GitHub repository someone clones and reads, and a directory of readable
JSON is inspectable without running anything.

Secrets are stripped on the way in via `RunConfig.redacted()`. A run file
records which credentials were set and how long they were, never their
values, so a run directory is safe to commit.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analyzer import Finding
from .config import RunConfig
from .metrics import CallMetrics
from .scoring import CallScore, RunScore
from .transcript import Transcript
from .verifier import STATUS_QUARANTINED, STATUS_REJECTED, STATUS_UNVERIFIED, STATUS_VERIFIED

RUNS_DIR = Path("data/runs")

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")


class RunStore:
    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or new_run_id()
        self.directory = RUNS_DIR / self.run_id
        self.directory.mkdir(parents=True, exist_ok=True)

    # -- writing -----------------------------------------------------------

    def save_config(self, config: RunConfig) -> None:
        (self.directory / "config.json").write_text(
            json.dumps(config.redacted(), indent=2), encoding="utf-8"
        )

    def save_call(
        self,
        transcript: Transcript,
        metrics: CallMetrics,
        findings: list[Finding],
        score: CallScore,
        analysis_error: str | None = None,
        discarded: list[dict] | None = None,
    ) -> None:
        call_dir = self.directory / transcript.call_id
        call_dir.mkdir(parents=True, exist_ok=True)
        transcript.save(call_dir)
        payload = {
            "call_id": transcript.call_id,
            "scenario_id": transcript.scenario_id,
            "metrics": metrics.as_dict(),
            "findings": [f.as_dict() for f in findings],
            "score": score.as_dict(),
            "analysis_error": analysis_error,
            "discarded_candidates": discarded or [],
        }
        (call_dir / "analysis.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def save_summary(self, run_score: RunScore, call_scores: list[CallScore]) -> None:
        (self.directory / "summary.json").write_text(
            json.dumps(
                {
                    "run_id": self.run_id,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "run_score": run_score.as_dict(),
                    "calls": [c.as_dict() for c in call_scores],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    # -- reading -----------------------------------------------------------

    @staticmethod
    def list_runs() -> list[str]:
        if not RUNS_DIR.exists():
            return []
        return sorted((d.name for d in RUNS_DIR.iterdir() if d.is_dir()), reverse=True)

    def load_calls(self) -> list[dict[str, Any]]:
        results = []
        for call_dir in sorted(self.directory.iterdir()):
            analysis = call_dir / "analysis.json"
            if call_dir.is_dir() and analysis.exists():
                results.append(json.loads(analysis.read_text(encoding="utf-8")))
        return results

    def load_summary(self) -> dict[str, Any] | None:
        path = self.directory / "summary.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def build_bug_report(
    run_id: str,
    calls: list[dict[str, Any]],
    run_score: RunScore,
) -> str:
    """
    Markdown bug report, ordered by severity.

    Quarantined and unverified findings appear in their own section rather
    than being deleted. A reviewer should be able to see what the system
    suspected but could not stand behind; that is more useful than a clean
    list that quietly hides its uncertainty.
    """
    verified: list[tuple[dict, dict]] = []
    withheld: list[tuple[dict, dict]] = []

    for call in calls:
        for finding in call.get("findings", []):
            status = finding.get("verification", {}).get("status")
            if status == STATUS_VERIFIED:
                verified.append((call, finding))
            elif status in (STATUS_UNVERIFIED, STATUS_QUARANTINED):
                withheld.append((call, finding))

    verified.sort(key=lambda pair: (SEVERITY_ORDER.get(pair[1]["severity"], 9), pair[1]["call_id"]))

    lines: list[str] = [
        "# Bug Report",
        "",
        f"Run: `{run_id}`  ",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"Calls analysed: {len(calls)}  ",
        f"Verified findings: {len(verified)}  ",
        f"Withheld findings: {len(withheld)}",
        "",
        "## How to read this",
        "",
        "Every finding below cites a transcript turn index and quotes the agent verbatim. "
        "Findings reached this list only after passing four verification gates: schema and "
        "speaker checks, a deterministic verbatim match against the transcript, a fact-dependency "
        "check, and independent adjudication sampled "
        "several times. Confidence is the adjudicator's mean confidence multiplied by its "
        "agreement rate across samples.",
        "",
        f"Of {len(verified) + len(withheld)} proposed findings, {len(withheld)} were withheld from "
        f"scoring. {run_score.hallucination_rate:.1%} failed verification outright; the remainder "
        "were quarantined for depending on a fact about the practice that is not on file. Both "
        "kinds are listed below rather than deleted.",
        "",
        "---",
        "",
        "## Verified findings",
        "",
    ]

    if not verified:
        lines.append("_No findings survived verification in this run._")
        lines.append("")
    else:
        for position, (call, finding) in enumerate(verified, start=1):
            verification = finding.get("verification", {})
            recording = f"data/recordings/{call['call_id']}.mp3"
            lines.extend(
                [
                    f"### {position}. {finding['title']}",
                    "",
                    f"**Severity:** {finding['severity'].upper()}  ",
                    f"**Dimension:** {finding['dimension'].replace('_', ' ')}  ",
                    f"**Confidence:** {verification.get('confidence', 0):.2f} "
                    f"({verification.get('agreement_rate', 0):.0%} adjudicator agreement)  ",
                    f"**Call:** `{call['call_id']}` (scenario {finding['scenario_id']}), turn {finding['turn_index']}  ",
                    f"**Transcript:** `data/runs/{run_id}/{call['call_id']}/{call['call_id']}_transcript.txt`  ",
                    f"**Recording:** `{recording}`",
                    "",
                    "**Agent said:**",
                    "",
                    f"> {finding['evidence_quote']}",
                    "",
                    f"**What happened:** {finding['what_happened']}",
                    "",
                    f"**Why it matters:** {finding['why_it_matters']}",
                    "",
                    f"**Expected behaviour:** {finding['expected_behaviour']}",
                    "",
                    "---",
                    "",
                ]
            )

    lines.extend(["## Withheld findings", ""])
    if not withheld:
        lines.append("_Nothing was withheld in this run._")
        lines.append("")
    else:
        lines.append(
            "These were proposed by the analyst but did not clear verification. They are listed "
            "for completeness and they contributed nothing to any score."
        )
        lines.append("")
        for call, finding in withheld:
            verification = finding.get("verification", {})
            lines.append(
                f"- **{finding['title']}** ({finding['severity']}, `{call['call_id']}` turn "
                f"{finding['turn_index']}) — {verification.get('status')}: {verification.get('summary', '')}"
            )
        lines.append("")

    lines.extend(
        [
            "## Run totals",
            "",
            "| Metric | Value |",
            "| --- | --- |",
            f"| Calls scored | {run_score.calls_scored} |",
            f"| Mean simulator quality | {run_score.mean_simulator_score:.1f} / 100 |",
            f"| Mean agent quality | {run_score.mean_agent_score:.1f} / 100 |",
            f"| Verified findings | {run_score.verification_counts.get(STATUS_VERIFIED, 0)} |",
            f"| Unverified | {run_score.verification_counts.get(STATUS_UNVERIFIED, 0)} |",
            f"| Quarantined | {run_score.verification_counts.get(STATUS_QUARANTINED, 0)} |",
            f"| Rejected | {run_score.verification_counts.get(STATUS_REJECTED, 0)} |",
            f"| Candidate filter rate | {run_score.hallucination_rate:.1%} |",
            "",
        ]
    )
    return "\n".join(lines)


def write_bug_report(run_id: str, calls: list[dict], run_score: RunScore, destination: Path | None = None) -> Path:
    path = destination or (RUNS_DIR / run_id / "bug_report.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_bug_report(run_id, calls, run_score), encoding="utf-8")
    return path
