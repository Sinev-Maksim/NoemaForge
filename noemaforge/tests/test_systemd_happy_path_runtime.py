#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_systemd_happy_path_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate systemd happy-path runtime behavior.
Inputs: Workspace systemd-happy-path policy, boot-mode helper and CLI wrapper.
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

import production_ai_contracts as pac
import systemd_happy_path_runtime as shpr


class SystemdHappyPathRuntimeTests(unittest.TestCase):
    def test_workspace_systemd_happy_path_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "systemd-happy-path-policy.json"
        validation = shpr.validate_systemd_happy_path_policy(
            shpr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])
        self.assertGreaterEqual(validation["metrics"]["boundary_refs"], 8)

        gate = pac.evaluate_gate(
            {"change_id": "systemd-happy-path-core", "domain": "pipeline"},
            shpr.systemd_happy_path_report_to_gate_evidence(validation, artifact_uri="reports/systemd-happy-path.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_boot_mode_helper_owns_install_units_apply_and_dry_run(self) -> None:
        text = (ROOT / "tools" / "prep" / "noemaforge-boot-mode.sh").read_text(encoding="utf-8")
        self.assertIn("install-units [--dry-run]", text)
        self.assertIn("--apply-systemd|--enable-autostart|--enable", text)
        self.assertIn("install -D -m 0644", text)
        self.assertIn("systemctl daemon-reload", text)
        self.assertIn("install-units)", text)
        self.assertIn("apply_systemd()", text)

    def test_cli_exposes_boot_mode_wrapper_instead_of_editor_path(self) -> None:
        cli = (ROOT / "bin" / "noemaforge").read_text(encoding="utf-8")
        self.assertIn("noemaforge boot-mode show|status", cli)
        self.assertIn("sudo noemaforge boot-mode set manual|gui|wogui", cli)
        self.assertIn("cmd_boot_mode", cli)
        self.assertNotIn("systemctl edit", cli)

    def test_examples_reject_manual_unit_editing_steps(self) -> None:
        policy = shpr.load_policy(ROOT / "configs" / "systemd-happy-path-policy.json")
        examples = shpr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "systemd_happy_path.example.json")
        blocked = policy["policy"]["blocked_happy_path_tokens"]
        scenario = examples["scenarios"][0]
        self.assertIn("sudo noemaforge boot-mode set gui --apply-systemd", scenario["happy_path_commands"])
        self.assertIn("sudo noemaforge boot-mode install-units --dry-run", scenario["happy_path_commands"])
        for step in scenario["rejected_manual_steps"]:
            self.assertTrue(any(token.lower() in step.lower() for token in blocked), step)


if __name__ == "__main__":
    unittest.main()
