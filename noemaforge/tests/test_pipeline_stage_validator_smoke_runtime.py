#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_stage_validator_smoke_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Unit-test offline pipeline stage validators and smoke commands.
Inputs: Pipeline runtime helpers and stage-validator smoke policy.
Outputs: unittest assertions only.
Side effects: Creates temporary directories only.
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

import pipeline_runtime as pr
import pipeline_stage_validator_smoke_runtime as psvs


def call_pipeline(argv: list[str]) -> tuple[int, dict]:
    stdout = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(stdout):
        try:
            pr.main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    gc.collect()
    raw = stdout.getvalue().strip()
    return code, json.loads(raw) if raw else {}


def make_run(tmp: Path, run_id: str = "run_stage_validator") -> tuple[Path, dict]:
    state = tmp / "state"
    code, created = call_pipeline([
        "run",
        "public_mwp",
        "--task-id",
        "stage_validator",
        "--run-id",
        run_id,
        "--request",
        "stage validator smoke test",
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
        "# orient\n\nDecision: validator smoke ready.\n\nRisk: low.\n\nNext handoff: status_check.\n\nEvidence: local stage validator test.\n",
        encoding="utf-8",
    )
    return output


class PipelineStageValidatorSmokeRuntimeTests(unittest.TestCase):
    def test_policy_validates_runtime_smoke_contract(self) -> None:
        report = psvs.validate_pipeline_stage_validator_smoke_policy(
            psvs.load_policy(),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
        )
        self.assertTrue(report["ok"], report["failures"])
        self.assertTrue(report["summary"]["ready_stage_guard"])
        self.assertTrue(report["summary"]["unready_stage_guard"])
        self.assertGreaterEqual(report["summary"]["smoke_case_count"], 5)

    def test_stage_validate_reports_unready_without_live_services(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            state, created = make_run(Path(raw), "run_stage_validator_unready")
            code, report = call_pipeline(["stage-validate", created["run_id"], "--stage", "orient", "--state", str(state), "--root", str(ROOT)])
            strict_code, strict_report = call_pipeline(["stage-validate", created["run_id"], "--stage", "orient", "--strict", "--state", str(state), "--root", str(ROOT)])

        self.assertEqual(0, code)
        self.assertTrue(report["ok"])
        self.assertFalse(report["stages"][0]["ready_to_advance"])
        self.assertIn("orient:contract_artifact_registered", report["warnings"])
        self.assertEqual(1, strict_code)
        self.assertIn("orient", strict_report["strict_ready_failures"])
        self.assertTrue(report["offline_only"])
        self.assertTrue(report["no_llm_autostart"])

    def test_ready_stage_passes_strict_validator_with_contract_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            state, created = make_run(Path(raw), "run_stage_validator_ready")
            output = write_ready_output(Path(created["run_dir"]))
            call_pipeline(["artifact", "add", created["run_id"], "--stage", "orient", "--type", "note", "--path", str(output), "--state", str(state), "--root", str(ROOT)])
            code, report = call_pipeline(["stage-validate", created["run_id"], "--stage", "orient", "--strict", "--state", str(state), "--root", str(ROOT)])

        self.assertEqual(0, code)
        stage = report["stages"][0]
        self.assertTrue(stage["ready_to_advance"])
        self.assertTrue(stage["typed_context_sidecar_ok"])
        self.assertTrue(stage["typed_context_sidecar_checksum_ok"])
        self.assertEqual(1, stage["contract_artifact_count"])
        self.assertTrue(stage["toolproxy_stage_binding"])

    def test_stage_smoke_command_uses_temp_state_and_passes(self) -> None:
        code, smoke = call_pipeline(["--root", str(ROOT), "stage-smoke"])
        self.assertEqual(0, code)
        self.assertTrue(smoke["ok"], smoke)
        cases = {case["id"]: case["ok"] for case in smoke["smoke_cases"]}
        self.assertTrue(cases["unready_stage_is_not_advanceable"])
        self.assertTrue(cases["ready_stage_is_advanceable"])
        self.assertTrue(cases["typed_sidecar_smoke_valid"])
        self.assertTrue(cases["contract_artifact_smoke_registered"])


if __name__ == "__main__":
    unittest.main()
