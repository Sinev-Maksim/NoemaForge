#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_dashboard_launcher_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate local dashboard launcher invariants.
Inputs: Workspace dashboard launcher policy and offline launcher fixtures.
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

import dashboard_launcher_runtime as dlr
import production_ai_contracts as pac


class DashboardLauncherRuntimeTests(unittest.TestCase):
    def test_workspace_dashboard_launcher_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "dashboard-launcher-policy.json"
        report = dlr.validate_dashboard_launcher_policy(
            dlr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(3, report["metrics"]["scenarios"])
        self.assertEqual(3, report["metrics"]["passing_scenarios"])
        self.assertEqual(9, report["metrics"]["required_cli_commands"])

        gate = pac.evaluate_gate(
            {"change_id": "dashboard-launcher-core", "domain": "pipeline"},
            dlr.dashboard_launcher_report_to_gate_evidence(report, artifact_uri="reports/dashboard-launcher.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_static_scan_confirms_state_writer_static_server_and_no_autostart(self) -> None:
        policy = dlr.load_policy(ROOT / "configs" / "dashboard-launcher-policy.json")
        report = dlr.validate_dashboard_launcher_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        checks = report["script_checks"]
        self.assertEqual(["autostart-disable", "autostart-enable", "autostart-status", "path", "serve", "start", "state", "status", "stop"], checks["commands"])
        self.assertTrue(checks["uses_dashboard_state_runtime"])
        self.assertTrue(checks["uses_admin_gui_server"])
        self.assertTrue(checks["uses_operator_state_home"])
        self.assertTrue(checks["uses_pidfile"])
        self.assertTrue(checks["localhost_url"])
        self.assertTrue(checks["user_systemd_autostart"])
        self.assertTrue(checks["user_autostart_enable"])
        self.assertTrue(checks["user_autostart_disable"])
        self.assertTrue(checks["user_autostart_status"])
        self.assertTrue(checks["autostart_dry_run"])
        self.assertTrue(checks["user_autostart_no_sudo"])
        self.assertEqual([], checks["llm_autostart_patterns"])
        self.assertEqual([], checks["media_autostart_patterns"])

    def test_missing_state_command_breaks_contract(self) -> None:
        policy = dlr.load_policy(ROOT / "configs" / "dashboard-launcher-policy.json")
        launcher = (ROOT / "tools" / "prep" / "noemaforge-dashboard.sh").read_text(encoding="utf-8")

        def fake_text(path: Path | str) -> str:
            text = Path(path).read_text(encoding="utf-8")
            if str(path).endswith("noemaforge-dashboard.sh"):
                return launcher.replace("path|state|serve|start|stop|status", "path|serve|start|stop|status")
            return text

        with patch.object(dlr, "load_text", side_effect=fake_text):
            report = dlr.validate_dashboard_launcher_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertFalse(report["ok"])
        self.assertIn("launcher_command_missing:state", report["failures"])

    def test_llm_autostart_pattern_breaks_contract(self) -> None:
        policy = dlr.load_policy(ROOT / "configs" / "dashboard-launcher-policy.json")

        def fake_text(path: Path | str) -> str:
            text = Path(path).read_text(encoding="utf-8")
            if str(path).endswith("noemaforge-dashboard.sh"):
                return text + "\nsystemctl start noemaforge-llama@main.service\n"
            return text

        with patch.object(dlr, "load_text", side_effect=fake_text):
            report = dlr.validate_dashboard_launcher_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertFalse(report["ok"])
        self.assertIn("launcher_llm_autostart_pattern_present", report["failures"])


if __name__ == "__main__":
    unittest.main()
