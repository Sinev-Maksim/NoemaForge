#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_selftest_trend_dashboard_qa.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test self-test trend dashboard discoverability through registry and docs.
Inputs: Unified Registry, self-test trend dashboard policy and canonical documentation files.
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

import selftest_trend_dashboard_runtime as stdr
import unified_registry_runtime as urr


class SelfTestTrendDashboardQATests(unittest.TestCase):
    def test_selftest_trend_dashboard_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:selftest-trend-dashboard-core:0.32.0")
        self.assertIsNotNone(pack)
        self.assertIn("configs/selftest-trend-dashboard-policy.json", pack["refs"])
        self.assertIn("contracts/selftest_trend_dashboard.schema.json", pack["refs"])
        self.assertIn("src/selftest_runtime.py", pack["refs"])
        self.assertIn("src/selftest_trend_dashboard_runtime.py", pack["refs"])
        self.assertIn("tests/test_selftest_trend_dashboard_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.31.13.alpha-patched1"]
        self.assertIn("eval-pack:selftest-trend-dashboard-core:0.32.0", pipeline["eval_pack_refs"])
        self.assertIn("configs/selftest-trend-dashboard-policy.json", pipeline["refs"])
        self.assertIn("src/selftest_runtime.py", pipeline["refs"])

    def test_selftest_trend_dashboard_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = stdr.load_policy(ROOT / "configs" / "selftest-trend-dashboard-policy.json")
        self.assertEqual("SelfTestTrendDashboardPolicy", policy["kind"])
        self.assertEqual("selftest_trend_dashboard", policy["policy"]["activation_state"])
        self.assertIn("trend", policy["policy"]["required_selftest_commands"])

        validation = stdr.validate_selftest_trend_dashboard_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(validation["ok"], validation["failures"])

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Add trend dashboard over multiple self-test reports.", text)
            self.assertIn("selftest-trend-dashboard-core", text)

        for path in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("selftest-trend-dashboard-core", text)
            self.assertIn("noemaforge selftest trend", text)


if __name__ == "__main__":
    unittest.main()

