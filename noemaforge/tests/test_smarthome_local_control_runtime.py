#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_smarthome_local_control_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate local-first SmartHome control invariants.
Inputs: Workspace SmartHome policy and temporary broken fixtures.
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

import production_ai_contracts as pac
import smarthome_local_control_runtime as shcr


class SmartHomeLocalControlRuntimeTests(unittest.TestCase):
    def test_workspace_smarthome_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "smarthome-local-control-policy.json"
        report = shcr.validate_smarthome_policy(
            shcr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["device_registries"])
        self.assertEqual(1, report["metrics"]["passing_device_registries"])
        self.assertEqual(2, report["metrics"]["actions"])
        self.assertEqual(2, report["metrics"]["passing_actions"])
        self.assertGreaterEqual(report["metrics"]["supported_devices"], 5)
        self.assertEqual(5, report["metrics"]["adapter_surfaces"])

        gate = pac.evaluate_gate(
            {"change_id": "smarthome-local-control-core", "domain": "pipeline"},
            shcr.smarthome_report_to_gate_evidence(report, artifact_uri="reports/smarthome-local-control.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_hidden_microphone_or_missing_privacy_state_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "smarthome-local-control-policy.json"
        policy = shcr.load_policy(policy_path)
        example_set = shcr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "smarthome_local_control.example.json")
        broken_set = copy.deepcopy(example_set)
        broken_set["device_registry"]["devices"][3]["microphone"] = True
        broken_set["device_registry"]["devices"][3]["visible_privacy_state"] = False

        with patch.object(shcr, "load_example_set", return_value=broken_set):
            report = shcr.validate_smarthome_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT, policy_path=policy_path)

        self.assertFalse(report["ok"])
        self.assertIn("microphone_capture_not_allowed:camera-door", report["failures"])
        self.assertIn("device_visible_privacy_state_missing:camera-door", report["failures"])

    def test_action_requires_emergency_pause_human_override_and_audit(self) -> None:
        policy_path = ROOT / "configs" / "smarthome-local-control-policy.json"
        policy = shcr.load_policy(policy_path)
        example_set = shcr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "smarthome_local_control.example.json")
        broken_set = copy.deepcopy(example_set)
        action = broken_set["actions"][0]
        action["emergency_pause_checked"] = False
        action["human_override_allowed"] = False
        action["audit_required"] = False

        with patch.object(shcr, "load_example_set", return_value=broken_set):
            report = shcr.validate_smarthome_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT, policy_path=policy_path)

        self.assertFalse(report["ok"])
        self.assertIn("action_emergency_pause_not_checked:turn-on-kettle-plug", report["failures"])
        self.assertIn("action_human_override_not_allowed:turn-on-kettle-plug", report["failures"])
        self.assertIn("action_audit_not_required:turn-on-kettle-plug", report["failures"])

    def test_required_adapter_surface_must_be_present_in_registry(self) -> None:
        policy_path = ROOT / "configs" / "smarthome-local-control-policy.json"
        policy = shcr.load_policy(policy_path)
        example_set = shcr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "smarthome_local_control.example.json")
        broken_set = copy.deepcopy(example_set)
        for device in broken_set["device_registry"]["devices"]:
            if device["adapter"] == "matter":
                device["adapter"] = "mqtt"

        with patch.object(shcr, "load_example_set", return_value=broken_set):
            report = shcr.validate_smarthome_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT, policy_path=policy_path)

        self.assertFalse(report["ok"])
        self.assertIn("device_registry_required_adapters_missing", report["failures"])


if __name__ == "__main__":
    unittest.main()
