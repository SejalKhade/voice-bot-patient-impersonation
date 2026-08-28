"""
Pipeline orchestration.

Owns the media server subprocess and drives calls one at a time. Sequential
by design: the assessment says all test calls come from a single phone
number, and two concurrent calls from one number would either collide at
the far end or produce transcripts whose latency figures are meaningless.

Progress is reported through a callback rather than printed, so the same
code path serves the Streamlit dashboard and the headless CLI without
either one owning the other.
"""

from __future__ import annotations

import atexit
import logging
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Iterable

import httpx

from . import ground_truth as gt
from .analyzer import Analyst, Finding
from .config import RunConfig
from .metrics import compute
from .scenarios import Scenario, by_id
from .scoring import CallScore, RunScore, score_call, score_run
from .store import RunStore, write_bug_report
from .transcript import Transcript
from .verifier import Verifier

log = logging.getLogger(__name__)

Progress = Callable[[str, str], None]  # (level, message); level in info|warn|error|step


def _noop(level: str, message: str) -> None:
    log.info("[%s] %s", level, message)


class MediaServer:
    """Supervises the uvicorn process that holds the phone calls open."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.process: subprocess.Popen | None = None
        self.base_url = f"http://127.0.0.1:{port}"

    def already_running(self) -> bool:
        try:
            return httpx.get(f"{self.base_url}/health", timeout=2.0).status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def start(self, progress: Progress = _noop) -> bool:
        if self.already_running():
            progress("info", f"Media server already listening on port {self.port}")
            return True

        log_file = Path("data/media_server.log").open("a", encoding="utf-8")
        self.process = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", "src.media_server:app",
                "--host", "0.0.0.0", "--port", str(self.port), "--log-level", "info",
            ],
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        atexit.register(self.stop)

        for _ in range(30):
            time.sleep(0.5)
            if self.already_running():
                progress("info", f"Media server started on port {self.port}")
                return True
        progress("error", "Media server did not become healthy within 15 seconds. Check data/media_server.log")
        return False

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


class Pipeline:
    def __init__(self, config: RunConfig, progress: Progress = _noop, run_id: str | None = None) -> None:
        self.config = config
        self.progress = progress
        self.store = RunStore(run_id)
        self.server = MediaServer(config.media_server_port)
        self.ground_truth = gt.load(config.ground_truth_path)
        self.store.save_config(config)

    # -- calling -----------------------------------------------------------

    def place_call(self, scenario: Scenario, call_id: str) -> Transcript | None:
        payload = {
            "scenario_id": scenario.id,
            "call_id": call_id,
            "config": _serialise(self.config),
        }
        try:
            response = httpx.post(f"{self.server.base_url}/calls", json=payload, timeout=45.0)
        except Exception as exc:  # noqa: BLE001
            self.progress("error", f"{scenario.id}: could not reach the media server: {exc}")
            return None

        if response.status_code >= 400:
            self.progress("error", f"{scenario.id}: dial failed: {response.text[:300]}")
            return None

        session_id = response.json()["session_id"]
        self.progress("info", f"{scenario.id}: dialing {self.config.target_number}")

        deadline = time.monotonic() + self.config.policy.max_call_seconds + 90
        seen = 0
        transcript_data = None

        while time.monotonic() < deadline:
            time.sleep(2.0)
            try:
                state = httpx.get(f"{self.server.base_url}/calls/{session_id}", timeout=15.0).json()
            except Exception:  # noqa: BLE001
                continue

            for line in state.get("log", [])[seen:]:
                self.progress("info", f"  {line}")
            seen = len(state.get("log", []))
            transcript_data = state.get("transcript")

            if state.get("status") in {"finished", "failed"}:
                # Give the recording fetcher a moment to attach its path.
                time.sleep(6)
                try:
                    state = httpx.get(f"{self.server.base_url}/calls/{session_id}", timeout=15.0).json()
                    transcript_data = state.get("transcript")
                except Exception:  # noqa: BLE001
                    pass
                break

        if not transcript_data:
            self.progress("error", f"{scenario.id}: no transcript was produced")
            return None

        transcript = Transcript.from_dict(transcript_data)
        self.progress(
            "info",
            f"{scenario.id}: call ended, {len(transcript.turns)} turns, "
            f"{transcript.duration_seconds():.0f}s",
        )
        return transcript

    # -- analysis -----------------------------------------------------------

    def analyse_call(self, transcript: Transcript, scenario: Scenario) -> tuple[list[Finding], CallScore, str | None, list[dict]]:
        metrics = compute(transcript, scenario)

        analyst = Analyst(self.config.anthropic_api_key, self.config.models, self.ground_truth)
        verifier = Verifier(self.config.anthropic_api_key, self.config.models, self.ground_truth)
        try:
            result = analyst.analyse(transcript, scenario)
            if result.error:
                self.progress("warn", f"{transcript.call_id}: analysis problem: {result.error}")

            if result.discarded:
                self.progress(
                    "warn",
                    f"{transcript.call_id}: {len(result.discarded)} candidate(s) failed gate 1 at extraction",
                )

            for finding in result.findings:
                verification = verifier.verify(finding, transcript)
                finding.verification = verification.as_dict()
                self.progress(
                    "info",
                    f"  {finding.id} [{finding.severity}] {verification.status} "
                    f"({verification.confidence:.2f}) {finding.title}",
                )

            score = score_call(metrics, result.findings)
            self.store.save_call(
                transcript, metrics, result.findings, score,
                analysis_error=result.error, discarded=result.discarded,
            )
            return result.findings, score, result.error, result.discarded
        finally:
            analyst.close()
            verifier.close()

    # -- full run ------------------------------------------------------------

    def run(self, scenario_ids: Iterable[str], analyse: bool = True) -> tuple[list[CallScore], RunScore]:
        scenario_ids = list(scenario_ids)
        if not self.server.start(self.progress):
            return [], score_run([], [])

        if not self.ground_truth.available:
            self.progress(
                "warn",
                "No ground truth on file. Factual claims will be quarantined rather than scored. "
                "See data/ground_truth.example.yaml.",
            )

        call_scores: list[CallScore] = []
        all_findings: list[Finding] = []

        for position, scenario_id in enumerate(scenario_ids, start=1):
            scenario = by_id(scenario_id)
            call_id = f"call_{position:02d}_{scenario.id}"
            self.progress("step", f"Call {position} of {len(scenario_ids)}: {scenario.id} {scenario.title}")

            transcript = self.place_call(scenario, call_id)
            if transcript is None:
                continue

            if analyse:
                findings, score, _, _ = self.analyse_call(transcript, scenario)
                all_findings.extend(findings)
                call_scores.append(score)
                self.progress(
                    "info",
                    f"{scenario.id}: simulator {score.simulator_score}/100, "
                    f"agent {score.agent_score:.1f}/100, "
                    f"{score.counts['verified']} verified of {score.counts['candidates']} candidates",
                )

            if position < len(scenario_ids):
                cooldown = self.config.policy.inter_call_cooldown_seconds
                self.progress("info", f"Cooling down {cooldown}s before the next call")
                time.sleep(cooldown)

        run_score = score_run(call_scores, all_findings)
        self.store.save_summary(run_score, call_scores)
        report = write_bug_report(self.store.run_id, self.store.load_calls(), run_score)
        self.progress("step", f"Run complete. Bug report written to {report}")
        return call_scores, run_score


def _serialise(config: RunConfig) -> dict:
    """Full config including secrets, sent only over localhost to our own server."""
    data = asdict(config)
    return data
