#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_stateful_admin_gui_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate stateful Admin GUI restore and surface hydration after installation.
Inputs: Workspace stateful-admin-gui policy and Admin GUI server runtime.
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

import stateful_admin_gui_runtime as sagr


class StatefulAdminGuiRuntimeTests(unittest.TestCase):
    def test_workspace_stateful_admin_gui_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "stateful-admin-gui-policy.json"
        report = sagr.validate_stateful_admin_gui_policy(
            sagr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(3, report["metrics"]["source_reports"])
        self.assertEqual(3, report["metrics"]["valid_source_reports"])
        self.assertEqual(6, report["metrics"]["surface_count"])

    def test_gui_state_restores_conversation_persona_tasks_jobs_telemetry_and_pipelines(self) -> None:
        fixture = sagr.build_stateful_gui_fixture(package_root=ROOT)
        gui_state = fixture["gui_state"]

        for section in ["conversation", "persona", "tasks", "jobs", "telemetry", "pipelines"]:
            self.assertIn(section, gui_state)
        self.assertEqual(fixture["conversation_current"]["conversation"]["conversation_id"], fixture["conversation_history"]["conversation_id"])
        self.assertGreaterEqual(len(fixture["conversation_history"]["messages"]), 2)
        self.assertEqual("Admin", fixture["persona"]["active_persona"])
        self.assertTrue(fixture["persona"]["portrait_url"].endswith(".svg"), fixture["persona"])
        self.assertFalse(fixture["persona"]["fallback"], fixture["persona"])
        self.assertGreaterEqual(fixture["tasks"]["summary"]["pending"], 1)
        self.assertGreaterEqual(fixture["tasks"]["summary"]["blocked"], 1)
        self.assertTrue(any(job["kind"] == "stateful_admin_gui_install_validation" for job in fixture["jobs"]["jobs"]))
        self.assertIn("hardware", fixture["telemetry"])
        self.assertGreater(len(fixture["pipelines"]["pipelines"]), 0)
        self.assertEqual("draft_only", fixture["pipelines"]["new_pipeline_supported"])

    def test_frontend_startup_uses_single_state_endpoint_then_refreshes_surfaces(self) -> None:
        app_js = (ROOT / "templates" / "pipeline-dashboard" / "app.js").read_text(encoding="utf-8")
        index_html = (ROOT / "templates" / "pipeline-dashboard" / "index.html").read_text(encoding="utf-8")

        for token in ["/api/gui/state", "renderConversation", "setPersona", "refreshTelemetry", "refreshTasks", "refreshJobs", "loadPipelines"]:
            self.assertIn(token, app_js)
        for dom_id in ["persona-portrait", "task-summary", "job-summary", "hardware-metrics", "runtime-metrics", "product-metrics", "pipeline-dock"]:
            self.assertIn(dom_id, index_html)


if __name__ == "__main__":
    unittest.main()
