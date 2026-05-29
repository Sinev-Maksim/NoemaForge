#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_share_automount_reboot_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the share automount reboot readiness contract.
Inputs: Share automount reboot readiness policy and runtime validator.
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

import share_automount_reboot_readiness_runtime as sarr


class ShareAutomountRebootReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_reboot(self) -> None:
        report = sarr.validate_share_automount_reboot_readiness_policy(sarr.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["share_reboot_readiness_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertTrue(summary["target_machine_required"])
        self.assertGreaterEqual(summary["target_command_count"], 10)
        self.assertIn("post_reboot_share_findmnt", report["evidence_requirements"])

    def test_reboot_plan_requires_operator_approval(self) -> None:
        payload = sarr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "operator-approved-reboot-plan":
                check["requires_operator_approval"] = False
        failures = sarr._policy_failures(broken)
        self.assertIn("check_operator_approval_required:operator-approved-reboot-plan", failures)

    def test_emergency_guard_requires_inactive_targets(self) -> None:
        payload = sarr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "post-reboot-emergency-guard":
                check["completion_gates"] = ["evidence_file_archived"]
        failures = sarr._policy_failures(broken)
        self.assertIn("check_emergency_guard_gate_missing:emergency_target_inactive", failures)
        self.assertIn("check_emergency_guard_gate_missing:rescue_target_inactive", failures)


if __name__ == "__main__":
    unittest.main()
