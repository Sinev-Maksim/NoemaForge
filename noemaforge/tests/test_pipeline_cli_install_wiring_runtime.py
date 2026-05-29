#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_cli_install_wiring_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Unit-test offline installer wiring validation for the public pipeline CLI.
Inputs: Pipeline CLI install wiring policy, setup script, installer and packaged CLI.
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

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import pipeline_cli_install_wiring_runtime as pciw


class PipelineCliInstallWiringRuntimeTests(unittest.TestCase):
    def test_policy_validates_existing_installer_and_cli_surface(self) -> None:
        report = pciw.validate_pipeline_cli_install_wiring_policy(
            pciw.load_policy(),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
        )
        self.assertTrue(report["ok"], report["failures"])
        summary = report["pipeline_cli_install_wiring_summary"]
        self.assertEqual(4, summary["public_symlink_count"])
        self.assertEqual(33, summary["pipeline_command_count"])
        self.assertTrue(summary["setup_selftest_cli"])
        self.assertTrue(summary["dry_run_link_plan"])
        self.assertTrue(summary["canonical_self_guard"])
        self.assertTrue(summary["pipeline_runtime_dispatch"])

    def test_rejects_missing_public_entrypoint_symlink(self) -> None:
        policy = copy.deepcopy(pciw.load_policy())
        policy["policy"]["required_install_symlinks"][0]["target_path"] = "/opt/noemaforge/bin/noemaforge-missing"
        report = pciw.validate_pipeline_cli_install_wiring_policy(
            policy,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
        )
        self.assertFalse(report["ok"])
        self.assertIn("installer_symlink_missing:/usr/local/bin/noemaforge", report["failures"])

    def test_rejects_missing_pipeline_command_contract(self) -> None:
        policy = copy.deepcopy(pciw.load_policy())
        policy["policy"]["required_pipeline_commands"].append("missing-command")
        report = pciw.validate_pipeline_cli_install_wiring_policy(
            policy,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
        )
        self.assertFalse(report["ok"])
        self.assertIn("cli_pipeline_command_missing:missing-command", report["failures"])
        self.assertIn("example_pipeline_command_missing:missing-command", report["failures"])

    def test_control_flags_remain_strict(self) -> None:
        policy = copy.deepcopy(pciw.load_policy())
        policy["policy"]["controls"]["no_live_install_execution"] = False
        failures = pciw._policy_failures(policy)
        self.assertIn("control_no_live_install_execution_not_true", failures)


if __name__ == "__main__":
    unittest.main()
