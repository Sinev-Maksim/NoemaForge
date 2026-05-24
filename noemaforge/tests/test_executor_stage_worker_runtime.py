#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_executor_stage_worker_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate contract-driven executor-step stage worker behavior.
Inputs: Workspace executor-stage-worker policy and synthetic pipeline runs.
Outputs: unittest assertions only.
Side effects: Temporary files under unittest temp directories only.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import contextlib
import gc
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import executor_stage_worker_runtime as eswr
import pipeline_runtime as prt
import production_ai_contracts as pac


def call_pipeline(argv: list[str]) -> tuple[int, dict]:
    stdout = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(stdout):
        try:
            prt.main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    gc.collect()
    return code, json.loads(stdout.getvalue())


def make_run(tmp: Path, run_id: str = "run_executor_stage_worker") -> tuple[Path, dict]:
    state = tmp / "state"
    code, created = call_pipeline([
        "run",
        "public_mwp",
        "--task-id",
        "executor_stage_worker",
        "--run-id",
        run_id,
        "--request",
        "executor stage worker test",
        "--state",
        str(state),
        "--root",
        str(ROOT),
    ])
    assert code == 0, created
    return state, created


def write_ready_output(run_dir: Path, stage: str = "orient") -> Path:
    output = run_dir / "outputs" / f"{stage}.md"
    output.write_text(
        "# orient\n\nDecision: continue.\n\nRisk: low.\n\nNext handoff: status_check.\n\nEvidence: synthetic executor stage worker test.\n",
        encoding="utf-8",
    )
    return output


class ExecutorStageWorkerRuntimeTests(unittest.TestCase):
    def test_workspace_executor_stage_worker_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "executor-stage-worker-policy.json"
        validation = eswr.validate_executor_stage_worker_policy(
            eswr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])

        gate = pac.evaluate_gate(
            {"change_id": "executor-stage-worker-core", "domain": "pipeline"},
            eswr.executor_stage_worker_report_to_gate_evidence(validation, artifact_uri="reports/executor-stage-worker.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_unready_apply_emits_wait_event_and_contract_shape(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            state, created = make_run(tmp, "run_unready_executor")
            code, step = call_pipeline(["executor-step", created["run_id"], "--apply", "--state", str(state), "--root", str(ROOT)])
            _, events = call_pipeline(["event-log", "--run-id", created["run_id"], "--json", "--state", str(state), "--root", str(ROOT)])

        self.assertEqual(0, code)
        self.assertFalse(step["ready"])
        self.assertEqual("wait", step["action"])
        self.assertEqual("noemaforge.pipeline.executor-stage-worker/v1", step["worker_contract_version"])
        self.assertIn("note", step["stage_contract"]["artifact_types"])
        self.assertEqual(0, step["contract_artifact_count"])
        self.assertIn("pipeline_executor_wait", [item["event_type"] for item in events["items"]])

    def test_ready_stage_applies_only_with_contract_matching_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            state, created = make_run(tmp, "run_ready_executor")
            output = write_ready_output(Path(created["run_dir"]))
            call_pipeline(["artifact", "add", created["run_id"], "--stage", "orient", "--type", "note", "--path", str(output), "--state", str(state), "--root", str(ROOT)])
            code, step = call_pipeline(["executor-step", created["run_id"], "--apply", "--state", str(state), "--root", str(ROOT)])
            _, events = call_pipeline(["event-log", "--run-id", created["run_id"], "--json", "--state", str(state), "--root", str(ROOT)])

        self.assertEqual(0, code)
        self.assertTrue(step["ready"])
        self.assertEqual("advance", step["action"])
        self.assertEqual("status_check", step["current_stage"])
        self.assertEqual(1, step["contract_artifact_count"])
        self.assertIn("pipeline_executor_step", [item["event_type"] for item in events["items"]])

    def test_wrong_artifact_type_does_not_satisfy_stage_contract(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            state, created = make_run(tmp, "run_wrong_artifact_executor")
            output = write_ready_output(Path(created["run_dir"]))
            call_pipeline(["artifact", "add", created["run_id"], "--stage", "orient", "--type", "test_report", "--path", str(output), "--state", str(state), "--root", str(ROOT)])
            code, step = call_pipeline(["executor-step", created["run_id"], "--state", str(state), "--root", str(ROOT)])

        self.assertEqual(0, code)
        self.assertFalse(step["ready"])
        self.assertEqual(1, step["artifact_count"])
        self.assertEqual(0, step["contract_artifact_count"])
        self.assertIn("contract-matching", step["warnings"][0])


if __name__ == "__main__":
    unittest.main()
