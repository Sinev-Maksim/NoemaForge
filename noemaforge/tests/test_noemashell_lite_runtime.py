#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_noemashell_lite_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate NoemaShell Lite operator-shell invariants.
Inputs: Workspace NoemaShell Lite policy and temporary broken fixtures.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import noemashell_lite_runtime as nslr
import production_ai_contracts as pac


class NoemaShellLiteRuntimeTests(unittest.TestCase):
    def test_workspace_noemashell_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "noemashell-lite-policy.json"
        report = nslr.validate_noemashell_policy(
            nslr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["sessions"])
        self.assertEqual(1, report["metrics"]["passing_sessions"])
        self.assertEqual(6, report["metrics"]["required_surfaces"])
        self.assertEqual(8, report["metrics"]["operator_controls"])
        self.assertEqual(3, report["metrics"]["budget_profiles"])

        gate = pac.evaluate_gate(
            {"change_id": "noemashell-lite-core", "domain": "pipeline"},
            nslr.noemashell_report_to_gate_evidence(report, artifact_uri="reports/noemashell-lite.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_missing_active_worker_surface_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "noemashell-lite-policy.json"
        policy = nslr.load_policy(policy_path)
        example_set = nslr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "noemashell_lite.example.json")
        broken_set = copy.deepcopy(example_set)
        del broken_set["sessions"][0]["surfaces"]["active_worker"]

        with patch.object(nslr, "load_example_set", return_value=broken_set):
            report = nslr.validate_noemashell_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("session_surfaces_missing:noemashell-lite-primary-repair", report["failures"])
        self.assertIn("session_active_worker_role_invalid:noemashell-lite-primary-repair:", report["failures"])

    def test_hidden_privileged_action_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "noemashell-lite-policy.json"
        policy = nslr.load_policy(policy_path)
        example_set = nslr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "noemashell_lite.example.json")
        broken_set = copy.deepcopy(example_set)
        action = broken_set["sessions"][0]["privileged_actions"][0]
        action["requires_approval"] = False
        del action["visible_reason"]

        with patch.object(nslr, "load_example_set", return_value=broken_set):
            report = nslr.validate_noemashell_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn(
            "session_privileged_action_approval_missing:noemashell-lite-primary-repair:privileged:safe-mode:001",
            report["failures"],
        )
        self.assertIn(
            "session_privileged_action_visible_reason_missing:noemashell-lite-primary-repair:privileged:safe-mode:001",
            report["failures"],
        )

    def test_heavy_backend_autostart_or_parallel_worker_budget_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "noemashell-lite-policy.json"
        policy = nslr.load_policy(policy_path)
        example_set = nslr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "noemashell_lite.example.json")
        broken_set = copy.deepcopy(example_set)
        budget = broken_set["sessions"][0]["surfaces"]["resource_budgets"]
        budget["max_active_heavy_workers"] = 2
        budget["heavy_backend_autostart"] = True

        with patch.object(nslr, "load_example_set", return_value=broken_set):
            report = nslr.validate_noemashell_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("session_budget_max_heavy_invalid:noemashell-lite-primary-repair:2", report["failures"])
        self.assertIn("session_budget_heavy_autostart_allowed:noemashell-lite-primary-repair", report["failures"])


if __name__ == "__main__":
    unittest.main()
