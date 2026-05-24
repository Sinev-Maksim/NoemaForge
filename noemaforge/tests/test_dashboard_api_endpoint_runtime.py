#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_dashboard_api_endpoint_runtime.py
Zone: gui/control-plane
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the dedicated Admin GUI dashboard backend endpoint contract.
Inputs: Dashboard API endpoint runtime and policy.
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

import dashboard_api_endpoint_runtime as daer


class DashboardApiEndpointRuntimeTests(unittest.TestCase):
    def test_policy_validates_against_workspace(self) -> None:
        policy_path = ROOT / "configs" / "dashboard-api-endpoint-policy.json"
        report = daer.validate_dashboard_api_endpoint_policy(
            daer.load_json(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=ROOT / "configs" / "unified-registry.json",
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(3, report["metrics"]["api_paths"])
        self.assertEqual(7, report["metrics"]["required_sections"])

    def test_offline_dashboard_api_returns_required_sections(self) -> None:
        server = daer.build_offline_dashboard_server(package_root=ROOT)
        payload = server.dashboard_api()

        self.assertTrue(payload["ok"])
        self.assertEqual("/api/dashboard", payload["endpoint"])
        self.assertEqual("dashboard-api-endpoint-core", payload["dashboard_backend"]["contract"])
        for section in ["dashboard", "conversation", "tasks", "jobs", "persona", "pipelines", "telemetry"]:
            self.assertIn(section, payload)
        self.assertEqual("/api/dashboard", payload["dashboard"]["backend_endpoint"])
        self.assertEqual("/api/gui/state", payload["dashboard"]["compatibility_endpoint"])


if __name__ == "__main__":
    unittest.main()
