#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_nologin_recovery_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the target `/run/nologin` recovery readiness contract.
Inputs: Nologin recovery readiness policy and runtime validator.
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

import nologin_recovery_readiness_runtime as nrr


class NologinRecoveryReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_recovery(self) -> None:
        report = nrr.validate_nologin_recovery_readiness_policy(nrr.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["nologin_recovery_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertTrue(summary["target_machine_required"])
        self.assertGreaterEqual(summary["target_command_count"], 8)
        self.assertIn("post_recovery_nologin_absent", report["evidence_requirements"])

    def test_recovery_requires_operator_approval(self) -> None:
        payload = nrr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "abort-cleanup-plan":
                check["requires_operator_approval"] = False
        failures = nrr._policy_failures(broken)
        self.assertIn("check_operator_approval_required:abort-cleanup-plan", failures)

    def test_nologin_absence_gate_is_required(self) -> None:
        payload = nrr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "nologin-cleared-after-recovery":
                check["completion_gates"] = ["evidence_file_archived"]
        failures = nrr._policy_failures(broken)
        self.assertIn("check_nologin_absence_gate_missing", failures)


if __name__ == "__main__":
    unittest.main()
