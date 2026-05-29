#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_setup_front_door_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate setup front-door runtime behavior.
Inputs: Workspace Setup Front Door policy, setup.sh and offline example.
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
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import setup_front_door_runtime as sfd


class SetupFrontDoorRuntimeTests(unittest.TestCase):
    def test_workspace_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "setup-front-door-policy.json"
        validation = sfd.validate_setup_front_door_policy(
            sfd.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(3, validation["metrics"]["required_modes"])
        self.assertEqual(6, validation["metrics"]["required_flags"])
        self.assertEqual(8, validation["metrics"]["phase_markers"])

    def test_example_contract_has_all_modes_flags_and_phases(self) -> None:
        examples = sfd.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "setup_front_door.example.json")
        report = sfd.evaluate_setup_contract(examples["scenarios"][0]["setup_contract"])

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(3, report["metrics"]["required_modes"])
        self.assertEqual(6, report["metrics"]["required_flags"])
        self.assertEqual(8, report["metrics"]["phase_markers"])

    def test_setup_script_prints_single_command_progress_phases(self) -> None:
        setup = (PROJECT_ROOT / "setup.sh").read_text(encoding="utf-8")
        installer = (PROJECT_ROOT / "install_noemaforge_0.32.1_mvp.sh").read_text(encoding="utf-8")
        analysis = sfd.analyze_setup_front_door(setup, installer)

        self.assertTrue(analysis["ok"], analysis["failures"])
        self.assertIn("seed_copy", analysis["phase_markers"])
        self.assertIn("reboot_pending", analysis["phase_markers"])
        self.assertIn("progress_output", analysis["wrapper_markers"])


if __name__ == "__main__":
    unittest.main()
