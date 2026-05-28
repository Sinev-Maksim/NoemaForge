#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_selftest_rss_slope_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test self-test RSS slope pack discoverability through registry and docs.
Inputs: Unified Registry, RSS slope policy and canonical documentation files.
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

import selftest_rss_slope_runtime as rsr
import unified_registry_runtime as urr


class SelfTestRssSlopeQATests(unittest.TestCase):
    def test_selftest_rss_slope_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:selftest-rss-slope-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/selftest-rss-slope-policy.json", pack["refs"])
        self.assertIn("contracts/selftest_rss_slope.schema.json", pack["refs"])
        self.assertIn("src/selftest_runtime.py", pack["refs"])
        self.assertIn("src/selftest_rss_slope_runtime.py", pack["refs"])
        self.assertIn("tests/test_selftest_rss_slope_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:selftest-rss-slope-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/selftest-rss-slope-policy.json", pipeline["refs"])
        self.assertIn("src/selftest_rss_slope_runtime.py", pipeline["refs"])

    def test_selftest_rss_slope_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = rsr.load_policy(ROOT / "configs" / "selftest-rss-slope-policy.json")
        self.assertEqual("SelfTestRssSlopePolicy", policy["kind"])
        self.assertEqual("rss_slope_stress_repeat_runner", policy["policy"]["activation_state"])
        self.assertIn("stress", policy["policy"]["required_selftest_commands"])

        validation = rsr.validate_selftest_rss_slope_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(validation["ok"], validation["failures"])

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Add stress/repeat runner for RSS-slope memory leak detection in 0.31.x.", text)
            self.assertIn("selftest-rss-slope-core", text)

        for path in [
            PROJECT_ROOT / "docs" / "README.md",
            ROOT / "docs" / "README.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("selftest-rss-slope-core", text)
            self.assertIn("noemaforge selftest stress", text)


if __name__ == "__main__":
    unittest.main()

