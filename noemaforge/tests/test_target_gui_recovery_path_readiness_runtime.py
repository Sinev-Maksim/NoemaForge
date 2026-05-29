#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_target_gui_recovery_path_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the target GUI recovery path readiness contract.
Inputs: Target GUI recovery path readiness policy and runtime validator.
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

import target_gui_recovery_path_readiness_runtime as tgr


class TargetGuiRecoveryPathReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_recovery(self) -> None:
        report = tgr.validate_target_gui_recovery_path_readiness_policy(tgr.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["target_gui_recovery_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["target_machine_required"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertGreaterEqual(summary["target_command_count"], 10)
        self.assertIn("pause_command_transcript", report["evidence_requirements"])
        self.assertIn("post_rescue_nologin_state", report["evidence_requirements"])

    def test_pause_and_rescue_require_operator_approval(self) -> None:
        payload = tgr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "pause-command-capture":
                check["requires_operator_approval"] = False
        failures = tgr._policy_failures(broken)
        self.assertIn("check_operator_approval_required:pause-command-capture", failures)

    def test_remote_upload_path_is_rejected(self) -> None:
        payload = tgr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "gui-recovery-archive":
                check["commands"].append("sudo noemaforge forensics --upload")
        failures = tgr._policy_failures(broken)
        self.assertIn("check_forbidden_token:gui-recovery-archive:--upload", failures)

    def test_gate_evidence_report_is_bounded_and_explicit(self) -> None:
        report = tgr.validate_target_gui_recovery_path_readiness_policy(tgr.load_policy())
        evidence = tgr.gate_evidence(
            report,
            artifact_uri="reports/target-gui-recovery-path-readiness.json",
        )
        self.assertEqual("target_gui_recovery_path_readiness", evidence["gate"])
        self.assertEqual("passed", evidence["status"])
        self.assertEqual(report["metrics"], evidence["metrics"])


if __name__ == "__main__":
    unittest.main()
