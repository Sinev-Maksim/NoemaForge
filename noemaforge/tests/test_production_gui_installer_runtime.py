#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_production_gui_installer_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the production GUI installer readiness contract.
Inputs: Production GUI installer policy, setup/installer scripts and systemd units.
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

import production_gui_installer_runtime as pgi


class ProductionGuiInstallerRuntimeTests(unittest.TestCase):
    def test_workspace_production_gui_installer_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "production-gui-installer-policy.json"
        report = pgi.validate_production_gui_installer_policy(
            pgi.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(3, report["metrics"]["gui_assets"])
        self.assertEqual(5, report["metrics"]["gui_units"])
        self.assertEqual(6, report["metrics"]["existing_contracts"])
        self.assertEqual(1, report["metrics"]["passing_scenarios"])

    def test_installer_surface_is_dry_run_root_guarded_and_timer_driven(self) -> None:
        policy = pgi.load_policy(ROOT / "configs" / "production-gui-installer-policy.json")
        surface = pgi.analyze_installer_surface(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertTrue(surface["ok"], surface["failures"])
        self.assertTrue(surface["flags"]["dry_run_first"])
        self.assertTrue(surface["flags"]["root_guarded_install"])
        self.assertTrue(surface["flags"]["timer_driven_gui_autostart"])
        self.assertTrue(surface["flags"]["runtime_only_gui"])
        self.assertTrue(surface["flags"]["no_heavy_llm_autostart"])

    def test_gui_service_is_not_directly_installable(self) -> None:
        service = (ROOT / "systemd" / "noemaforge-autostart-gui.service").read_text(encoding="utf-8")
        timer = (ROOT / "systemd" / "noemaforge-autostart-gui.timer").read_text(encoding="utf-8")

        self.assertNotIn("[Install]", service)
        self.assertIn("Do not enable this service directly", service)
        self.assertIn("OnBootSec=3min", timer)
        self.assertIn("WantedBy=timers.target", timer)


if __name__ == "__main__":
    unittest.main()
