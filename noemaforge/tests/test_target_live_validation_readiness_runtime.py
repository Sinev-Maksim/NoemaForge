#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_target_live_validation_readiness_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Runtime-test the target live validation readiness contract.
Inputs: Target live validation readiness policy and runtime validator.
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

import target_live_validation_readiness_runtime as tlv


class TargetLiveValidationReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_running_live_commands(self) -> None:
        report = tlv.validate_target_live_validation_readiness_policy(tlv.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        self.assertTrue(report["readiness_summary"]["completion_blocked"])
        self.assertTrue(report["readiness_summary"]["safe_local_validator_only"])
        self.assertGreaterEqual(report["readiness_summary"]["target_command_count"], 10)
        self.assertIn("manual_llm_approval_gate", tlv.REQUIRED_OUTPUTS)

    def test_llm_start_requires_operator_approval(self) -> None:
        payload = tlv.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "main-llm-manual-smoke":
                check["requires_operator_approval"] = False
        failures = tlv._policy_failures(broken)
        self.assertIn("check_llm_start_without_operator_approval:main-llm-manual-smoke", failures)

    def test_missing_primary_live_todo_is_rejected(self) -> None:
        payload = tlv.load_policy()
        broken = copy.deepcopy(payload)
        broken["policy"]["blocked_todo_refs"] = []
        failures = tlv._policy_failures(broken)
        self.assertIn("policy_primary_blocked_todo_missing", failures)


if __name__ == "__main__":
    unittest.main()
