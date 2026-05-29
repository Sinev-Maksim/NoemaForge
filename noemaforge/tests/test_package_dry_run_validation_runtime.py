#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_package_dry_run_validation_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate install/uninstall dry-run package validation invariants.
Inputs: Workspace package dry-run policy and offline dry-run fixtures.
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
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import package_dry_run_validation_runtime as pdvr
import production_ai_contracts as pac


class PackageDryRunValidationRuntimeTests(unittest.TestCase):
    def test_workspace_package_dry_run_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "package-dry-run-validation-policy.json"
        report = pdvr.validate_package_dry_run_policy(
            pdvr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(2, report["metrics"]["scenarios"])
        self.assertEqual(2, report["metrics"]["passing_scenarios"])
        self.assertEqual(5, report["metrics"]["required_setup_flags"])
        self.assertEqual(2, report["metrics"]["required_uninstall_flags"])

        gate = pac.evaluate_gate(
            {"change_id": "package-dry-run-validation-core", "domain": "pipeline"},
            pdvr.package_dry_run_report_to_gate_evidence(report, artifact_uri="reports/package-dry-run-validation.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_static_scan_confirms_setup_and_uninstall_dry_run_surfaces(self) -> None:
        policy = pdvr.load_policy(ROOT / "configs" / "package-dry-run-validation-policy.json")
        report = pdvr.validate_package_dry_run_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        setup = report["script_checks"]["setup"]
        uninstall = report["script_checks"]["uninstall"]
        self.assertLess(setup["dry_run_if_line"], setup["installer_exec_line"])
        self.assertTrue(setup["root_guard"])
        self.assertTrue(setup["recursion_guard"])
        self.assertEqual([], setup["dangerous_tokens"])
        self.assertTrue(uninstall["dry_run_complete"])
        self.assertTrue(uninstall["no_destructive_actions_report"])

    def test_missing_setup_dry_run_flag_breaks_contract(self) -> None:
        policy = pdvr.load_policy(ROOT / "configs" / "package-dry-run-validation-policy.json")
        original = (PROJECT_ROOT / "setup.sh").read_text(encoding="utf-8")

        def fake_script(path: Path | str) -> str:
            text = Path(path).read_text(encoding="utf-8")
            if str(path).endswith("setup.sh"):
                return original.replace("--dry-run", "--plan-only")
            return text

        with patch.object(pdvr, "load_script_text", side_effect=fake_script):
            report = pdvr.validate_package_dry_run_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertFalse(report["ok"])
        self.assertIn("setup_flag_missing:--dry-run", report["failures"])

    def test_uninstall_destructive_action_breaks_contract(self) -> None:
        policy = pdvr.load_policy(ROOT / "configs" / "package-dry-run-validation-policy.json")

        def fake_script(path: Path | str) -> str:
            text = Path(path).read_text(encoding="utf-8")
            if str(path).endswith("uninstall_noemaforge_0.32.2_mvp.sh"):
                return text + "\nrm -rf /opt/noemaforge\n"
            return text

        with patch.object(pdvr, "load_script_text", side_effect=fake_script):
            report = pdvr.validate_package_dry_run_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertFalse(report["ok"])
        self.assertIn("uninstall_rm_rf_present_in_dry_run_surface", report["failures"])


if __name__ == "__main__":
    unittest.main()
