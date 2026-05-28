#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_live_testbench_suite_readiness_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the live testbench suite readiness contract.
Inputs: Live testbench readiness policy and runtime validator.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import live_testbench_suite_readiness_runtime as ltsr


class LiveTestbenchSuiteReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_running_live_suite(self) -> None:
        report = ltsr.validate_live_testbench_suite_readiness_policy(ltsr.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["live_testbench_suite_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["target_machine_required"])
        self.assertTrue(summary["operator_approval_required"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertGreaterEqual(summary["target_command_count"], 15)
        self.assertIn("live_testbench_stdout_json", report["evidence_requirements"])
        self.assertIn("duration_sec_metrics", report["evidence_requirements"])
        self.assertIn("baseline_compare_json", report["evidence_requirements"])

    def test_live_run_must_keep_include_live_flag(self) -> None:
        broken = copy.deepcopy(ltsr.load_policy())
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "live-suite-run":
                check["commands"] = ["noemaforge testbench run --suite live --json"]
        failures = ltsr._policy_failures(broken)
        self.assertIn("check_command_missing:live-suite-run:noemaforge testbench run --suite live --include-live --json", failures)
        self.assertIn("check_include_live_flag_missing:live-suite-run", failures)

    def test_operator_approval_is_required_for_live_run_and_archive_steps(self) -> None:
        broken = copy.deepcopy(ltsr.load_policy())
        for check in broken["policy"]["required_checks"]:
            if check["id"] in {"live-suite-run", "baseline-compare-and-archive"}:
                check["requires_operator_approval"] = False
        failures = ltsr._policy_failures(broken)
        self.assertIn("check_operator_approval_required:live-suite-run", failures)
        self.assertIn("check_operator_approval_required:baseline-compare-and-archive", failures)

    def test_remote_upload_path_is_rejected(self) -> None:
        broken = copy.deepcopy(ltsr.load_policy())
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "baseline-compare-and-archive":
                check["commands"].append("noemaforge wiki-patch create --upload")
        failures = ltsr._policy_failures(broken)
        self.assertIn("check_forbidden_token:baseline-compare-and-archive:--upload", failures)

    def test_example_validation_and_gate_evidence_are_explicit(self) -> None:
        report = ltsr.validate_live_testbench_suite_readiness_policy(ltsr.load_policy())
        example = ltsr.validate_example()
        self.assertTrue(example["ok"], example["failures"])
        evidence = ltsr.gate_evidence(report, artifact_uri="reports/live-testbench-suite-readiness.json")
        self.assertEqual("live_testbench_suite_readiness", evidence["gate"])
        self.assertEqual("passed", evidence["status"])
        self.assertEqual(report["metrics"], evidence["metrics"])


if __name__ == "__main__":
    unittest.main()
