#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_dashboard_launcher_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test dashboard launcher discoverability through registry and docs.
Inputs: Unified Registry, dashboard launcher policy and canonical documentation files.
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

import dashboard_launcher_runtime as dlr
import unified_registry_runtime as urr


class DashboardLauncherQATests(unittest.TestCase):
    def test_dashboard_launcher_pack_is_registered_and_attached_to_pipeline(self) -> None:
        registry_path = ROOT / "configs" / "unified-registry.json"
        report = urr.validate_unified_registry(
            urr.load_registry(registry_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=registry_path,
        )
        self.assertTrue(report["ok"], report["failures"])

        entries = {
            f"{entry['kind']}:{entry['id']}:{entry['version']}": entry
            for entry in report["normalized_registry"]["entries"]
        }
        pack = entries.get("eval-pack:dashboard-launcher-core:0.32.2")
        self.assertIsNotNone(pack)
        self.assertIn("configs/dashboard-launcher-policy.json", pack["refs"])
        self.assertIn("contracts/dashboard_launcher.schema.json", pack["refs"])
        self.assertIn("src/dashboard_launcher_runtime.py", pack["refs"])
        self.assertIn("tests/test_dashboard_launcher_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.2"]
        self.assertIn("eval-pack:dashboard-launcher-core:0.32.2", pipeline["eval_pack_refs"])
        self.assertIn("configs/dashboard-launcher-policy.json", pipeline["refs"])
        self.assertIn("src/dashboard_launcher_runtime.py", pipeline["refs"])

    def test_dashboard_launcher_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = dlr.load_policy(ROOT / "configs" / "dashboard-launcher-policy.json")
        self.assertEqual("DashboardLauncherPolicy", policy["kind"])
        self.assertEqual("local_dashboard_launcher", policy["policy"]["activation_state"])
        self.assertEqual(
            ["path", "state", "serve", "start", "stop", "status", "autostart-enable", "autostart-disable", "autostart-status"],
            policy["policy"]["required_cli_commands"],
        )

        report = dlr.validate_dashboard_launcher_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Add local web dashboard launcher command.", text)
            self.assertIn("[x] Add local dashboard launcher command that writes dashboard-state and serves the static UI.", text)
            self.assertIn("[x] Add user-level dashboard autostart enable/disable commands.", text)
            self.assertIn("dashboard-launcher-core", text)

        for path in [
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("dashboard-launcher-core", text)
            self.assertIn("path/state/serve/start/stop/status", text)
            self.assertIn("user-level dashboard autostart", text)


if __name__ == "__main__":
    unittest.main()

