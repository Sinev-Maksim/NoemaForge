#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_setup_default_path_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate setup default-path runtime behavior.
Inputs: Workspace Setup Default Path policy, root setup.sh and offline example.
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

import setup_default_path_runtime as sdp


class SetupDefaultPathRuntimeTests(unittest.TestCase):
    def test_workspace_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "setup-default-path-policy.json"
        validation = sdp.validate_setup_default_path_policy(
            sdp.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(5, validation["metrics"]["canonical_steps"])
        self.assertEqual(4, validation["metrics"]["required_modes"])
        self.assertGreaterEqual(validation["metrics"]["onboarding_refs"], 4)

    def test_example_candidate_is_vm_first_and_windows_optional(self) -> None:
        examples = sdp.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "setup_default_path.example.json")
        report = sdp.evaluate_setup_candidate(examples["scenarios"][0]["candidate"])

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(0, report["metrics"]["requires_windows"])

    def test_setup_front_door_defaults_to_safe_vm_mode(self) -> None:
        setup = (PROJECT_ROOT / "setup.sh").read_text(encoding="utf-8")

        self.assertIn('MODE="vm"', setup)
        self.assertIn("./setup.sh --mode vm --dry-run --selftest", setup)
        self.assertIn("sudo ./setup.sh --mode host", setup)
        self.assertIn("non-dry-run install requires sudo/root", setup)
        self.assertNotIn("powershell", setup[setup.find("Recommended first public MWP path:"):setup.find("Notes:")].lower())


if __name__ == "__main__":
    unittest.main()
