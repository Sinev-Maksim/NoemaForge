#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_full_composite_target_run_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the patched10 full-composite target-run readiness contract.
Inputs: Full composite target-run readiness policy and runtime validator.
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

import full_composite_target_run_readiness_runtime as fcr


class FullCompositeTargetRunReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_first_start(self) -> None:
        report = fcr.validate_full_composite_target_run_readiness_policy(fcr.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["full_composite_readiness_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertGreaterEqual(summary["target_command_count"], 10)
        self.assertIn("composite_selection_plan", report["artifact_requirements"])

    def test_full_composite_command_requires_operator_approval(self) -> None:
        payload = fcr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "full-composite-run-transcript":
                check["requires_operator_approval"] = False
        failures = fcr._policy_failures(broken)
        self.assertIn("check_operator_approval_required:full-composite-run-transcript", failures)

    def test_full_composite_command_requires_zero_and_timeouts(self) -> None:
        payload = fcr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "full-composite-command-plan":
                check["commands"] = ["sudo noemaforge first-start --full_composite 4"]
        failures = fcr._policy_failures(broken)
        self.assertIn("check_full_composite_zero_missing:full-composite-command-plan", failures)
        self.assertIn("check_timeout_bounds_missing:full-composite-command-plan", failures)


if __name__ == "__main__":
    unittest.main()
