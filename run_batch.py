#!/usr/bin/env python3
"""
Headless runner.

Same pipeline the dashboard drives, without the interface. Useful for a long
overnight batch, and it keeps the dashboard honest: if the console ever grows
logic the CLI cannot reach, that logic is in the wrong place.

    python run_batch.py --scenarios S01 S02 S03
    python run_batch.py --all
    python run_batch.py --reanalyse run_20260826_101500
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.config import RunConfig
from src.orchestrator import Pipeline
from src.scenarios import SCENARIOS, by_id, default_selection
from src.scoring import score_run
from src.store import RunStore, write_bug_report
from src.transcript import load_transcript

LEVEL_MARKS = {"info": "  ", "warn": "! ", "error": "X ", "step": "> "}


def report(level: str, message: str) -> None:
    print(f"{LEVEL_MARKS.get(level, '  ')}{message}", flush=True)


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Voice QA batch runner")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--scenarios", nargs="+", metavar="ID", help="Scenario ids to run")
    group.add_argument("--all", action="store_true", help="Run the full catalogue")
    group.add_argument("--reanalyse", metavar="RUN_ID", help="Re-run analysis over stored transcripts")
    parser.add_argument("--list", action="store_true", help="List the catalogue and exit")
    args = parser.parse_args()

    if args.list:
        for scenario in SCENARIOS:
            print(f"  {scenario.id}  {scenario.title}")
            print(f"        {scenario.category} | {', '.join(scenario.tags)}")
        return 0

    config = RunConfig.from_env()

    if args.reanalyse:
        return reanalyse(config, args.reanalyse)

    problems = config.missing_requirements()
    if problems:
        print("Configuration incomplete:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print("\nCopy .env.example to .env and fill it in.", file=sys.stderr)
        return 1

    if args.all:
        scenario_ids = [s.id for s in SCENARIOS]
    elif args.scenarios:
        scenario_ids = args.scenarios
        for scenario_id in scenario_ids:
            by_id(scenario_id)  # raises on a typo before any money is spent
    else:
        scenario_ids = default_selection()

    print(f"Running {len(scenario_ids)} scenarios against {config.target_number}\n")

    pipeline = Pipeline(config, report)
    call_scores, run_score = pipeline.run(scenario_ids)

    print("\n" + "=" * 68)
    print(f"Run           : {pipeline.store.run_id}")
    print(f"Calls scored  : {run_score.calls_scored}")
    print(f"Simulator mean: {run_score.mean_simulator_score:.1f} / 100")
    print(f"Agent mean    : {run_score.mean_agent_score:.1f} / 100")
    print(f"Verified      : {run_score.verification_counts.get('verified', 0)}")
    print(f"Filtered out  : {run_score.hallucination_rate:.1%} of candidates")
    print(f"Report        : data/runs/{pipeline.store.run_id}/bug_report.md")
    print("=" * 68)
    return 0


def reanalyse(config: RunConfig, run_id: str) -> int:
    """
    Re-score stored transcripts without placing new calls.

    The reason this exists: after supplying ground truth, findings that were
    quarantined at gate 3 become checkable. Re-dialling the line to learn
    that would be wasteful and would not reproduce the same conversation.
    """
    if not config.anthropic_api_key:
        print("ANTHROPIC_API_KEY is required for analysis.", file=sys.stderr)
        return 1

    store = RunStore(run_id)
    if not store.directory.exists():
        print(f"No such run: {run_id}", file=sys.stderr)
        return 1

    pipeline = Pipeline(config, report, run_id=run_id)
    call_scores = []
    all_findings = []

    for call_dir in sorted(store.directory.iterdir()):
        if not call_dir.is_dir():
            continue
        candidates = list(call_dir.glob("*_transcript.json"))
        if not candidates:
            continue
        transcript = load_transcript(candidates[0])
        scenario = by_id(transcript.scenario_id)
        report("step", f"Re-analysing {transcript.call_id}")
        findings, score, _, _ = pipeline.analyse_call(transcript, scenario)
        all_findings.extend(findings)
        call_scores.append(score)

    run_score = score_run(call_scores, all_findings)
    store.save_summary(run_score, call_scores)
    path = write_bug_report(run_id, store.load_calls(), run_score)
    print(f"\nRe-analysis complete. Report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
