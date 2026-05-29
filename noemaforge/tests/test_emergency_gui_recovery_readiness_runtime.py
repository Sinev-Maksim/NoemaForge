#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_emergency_gui_recovery_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the emergency GUI recovery readiness contract.
Inputs: Emergency GUI recovery readiness policy and runtime validator.
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

import emergency_gui_recovery_readiness_runtime as egrr


class EmergencyGuiRecoveryReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_recovery(self) -> None:
        report = egrr.validate_emergency_gui_recovery_readiness_policy(egrr.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["emergency_gui_recovery_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["target_machine_required"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertGreaterEqual(summary["target_command_count"], 10)
        self.assertIn("display_manager_alias_state", report["evidence_requirements"])
        self.assertIn("post_rescue_nologin_absent", report["evidence_requirements"])

    def test_gui_rescue_requires_operator_approval(self) -> None:
        payload = egrr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "gui-rescue-wait":
                check["requires_operator_approval"] = False
        failures = egrr._policy_failures(broken)
        self.assertIn("check_operator_approval_required:gui-rescue-wait", failures)

    def test_display_manager_alias_gate_is_required(self) -> None:
        payload = egrr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "display-manager-gdm-alias":
                check["completion_gates"] = ["gdm_service_state_recorded", "evidence_file_archived"]
        failures = egrr._policy_failures(broken)
        self.assertIn("check_display_manager_alias_gate_missing", failures)

    def test_gate_evidence_report_is_bounded_and_explicit(self) -> None:
        report = egrr.validate_emergency_gui_recovery_readiness_policy(egrr.load_policy())
        evidence = egrr.gate_evidence(
            report,
            artifact_uri="reports/emergency-gui-recovery-readiness.json",
        )
        self.assertEqual("emergency_gui_recovery_readiness", evidence["gate"])
        self.assertEqual("passed", evidence["status"])
        self.assertEqual(report["metrics"], evidence["metrics"])


if __name__ == "__main__":
    unittest.main()
