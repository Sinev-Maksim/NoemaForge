#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_abstention_policy_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate the executable AbstentionPolicy runtime checks.
Inputs: Workspace policy plus in-memory broken policy fixtures.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import abstention_policy_runtime as apr


class AbstentionPolicyRuntimeTests(unittest.TestCase):
    def test_workspace_policy_validates_all_core_actions(self) -> None:
        policy_path = ROOT / "configs" / "abstention-policy.json"
        report = apr.validate_abstention_policy(apr.load_policy(policy_path), policy_path=policy_path)

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(8, report["metrics"]["scenario_total"])
        self.assertEqual(8, report["metrics"]["scenario_passed"])
        self.assertEqual(0, report["metrics"]["scenario_failed"])
        self.assertEqual(0, report["metrics"]["missing_actions"])
        actual = {row["id"]: row["actual_action"] for row in report["scenario_results"]}
        self.assertEqual("route", actual["route_low_risk_high_confidence"])
        self.assertEqual("ask_clarification", actual["ask_when_missing_context"])
        self.assertEqual("defer_ssr", actual["defer_ssr_when_high_risk"])
        self.assertEqual("block", actual["block_when_unsafe"])

    def test_policy_validation_blocks_bad_threshold_and_unknown_action(self) -> None:
        broken = {
            "apiVersion": "noemaforge.production-ai/v1",
            "kind": "AbstentionPolicy",
            "auto_route_min_confidence": 0.4,
            "clarify_min_confidence": 0.8,
            "high_risk_action": "handoff_maybe",
            "critical_risk_action": "block",
            "ungrounded_action": "defer_sr",
            "unsafe_action": "block",
            "actions": {"route": "Proceed."},
        }

        report = apr.validate_abstention_policy(broken)

        self.assertFalse(report["ok"])
        self.assertIn("clarify_threshold_above_auto_route", report["failures"])
        self.assertIn("high_risk_action_invalid:handoff_maybe", report["failures"])
        self.assertGreater(report["metrics"]["missing_actions"], 0)


if __name__ == "__main__":
    unittest.main()
