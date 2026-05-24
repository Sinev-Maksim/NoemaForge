#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_drive_state_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate Drive_State bounded modulation contracts.
Inputs: Workspace Drive State policy and temporary broken fixtures.
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

import drive_state_runtime as dsr
import production_ai_contracts as pac


class DriveStateRuntimeTests(unittest.TestCase):
    def test_workspace_drive_state_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "drive-state-policy.json"
        report = dsr.validate_drive_state_policy(
            dsr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["states"])
        self.assertEqual(1, report["metrics"]["passing_states"])
        self.assertEqual(1, report["metrics"]["modulation_cases"])
        self.assertEqual(1, report["metrics"]["passing_modulation_cases"])
        self.assertEqual(0, report["metrics"]["missing_refs"])

        gate = pac.evaluate_gate(
            {"change_id": "drive-state-governance-core", "domain": "pipeline"},
            dsr.drive_state_report_to_gate_evidence(report, artifact_uri="reports/drive-state.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_unbounded_signal_value_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "drive-state-policy.json"
        policy = dsr.load_policy(policy_path)
        example_set = dsr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "drive_state.example.json")
        state = example_set["states"][0]
        state["signals"]["pressure"] = 1.1

        with patch.object(dsr, "load_example_set", return_value=example_set):
            report = dsr.validate_drive_state_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("state_signal_out_of_bounds:drive-state-coarse-host-bounded:pressure:1.1", report["failures"])

    def test_missing_sense_ref_and_mutation_guards_are_blocked(self) -> None:
        policy_path = ROOT / "configs" / "drive-state-policy.json"
        policy = dsr.load_policy(policy_path)
        example_set = dsr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "drive_state.example.json")
        state = example_set["states"][0]
        state["sense_state_ref"] = ""
        state["guards"]["can_rewrite_goals"] = True
        state["guards"]["can_override_policy"] = True
        state["guards"]["can_expand_permissions"] = True
        state["privacy"]["source_filtered"] = False

        with patch.object(dsr, "load_example_set", return_value=example_set):
            report = dsr.validate_drive_state_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("state_sense_state_ref_missing:drive-state-coarse-host-bounded", report["failures"])
        self.assertIn("state_goal_rewrite_allowed:drive-state-coarse-host-bounded", report["failures"])
        self.assertIn("state_policy_override_allowed:drive-state-coarse-host-bounded", report["failures"])
        self.assertIn("state_permission_expansion_allowed:drive-state-coarse-host-bounded", report["failures"])
        self.assertIn("state_source_not_filtered:drive-state-coarse-host-bounded", report["failures"])

    def test_modulation_helper_clips_and_forbids_goal_or_policy_mutation(self) -> None:
        policy = dsr.load_policy(ROOT / "configs" / "drive-state-policy.json")
        sense_state = {
            "id": "sense-state-stressed",
            "trace_id": "trace:sense:stressed",
            "privacy": {"filtered": True, "local_only": True},
            "metrics": {
                "cpu": {"usage_percent": 999.0},
                "memory": {"pressure": "critical"},
                "disk": {"used_percent": 125.0},
                "network": {"state": "degraded"},
                "load": {"pressure": "critical"},
                "runtime": {"backend": "healthy", "gateway": "unhealthy"},
            },
        }

        drive_state = dsr.modulate_drive_state(sense_state, policy)

        self.assertEqual({"pressure", "fatigue", "urgency", "curiosity"}, set(drive_state["signals"]))
        for value in drive_state["signals"].values():
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)
        self.assertIn("slow_down", drive_state["modulation"]["actions"])
        self.assertIn("defer", drive_state["modulation"]["actions"])
        self.assertFalse(drive_state["guards"]["can_rewrite_goals"])
        self.assertFalse(drive_state["guards"]["can_override_policy"])
        self.assertFalse(drive_state["guards"]["can_expand_permissions"])


if __name__ == "__main__":
    unittest.main()
