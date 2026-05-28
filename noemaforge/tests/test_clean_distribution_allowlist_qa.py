#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_clean_distribution_allowlist_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Clean Distribution Allowlist discoverability through registry and canonical docs.
Inputs: Unified Registry, clean-distribution policy and canonical documentation files.
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

import clean_distribution_allowlist_runtime as cdar
import unified_registry_runtime as urr


class CleanDistributionAllowlistQATests(unittest.TestCase):
    def test_clean_distribution_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:clean-distribution-allowlist-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/clean-distribution-allowlist.json", pack["refs"])
        self.assertIn("src/clean_distribution_allowlist_runtime.py", pack["refs"])
        self.assertIn("tests/test_clean_distribution_allowlist_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:clean-distribution-allowlist-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/clean-distribution-allowlist.json", pipeline["refs"])
        self.assertIn("src/clean_distribution_allowlist_runtime.py", pipeline["refs"])

    def test_clean_distribution_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = cdar.load_policy(ROOT / "configs" / "clean-distribution-allowlist.json")
        self.assertEqual("CleanDistributionAllowlistPolicy", policy["kind"])
        self.assertEqual("allowlist_public_seed", policy["policy"]["activation_state"])
        self.assertTrue(policy["policy"]["build_policy"]["allowlist_only"])
        self.assertFalse(policy["policy"]["build_policy"]["include_transient_artifacts"])

        report = cdar.validate_clean_distribution_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Build public distributions from an allowlist", text)
            self.assertIn("Clean Distribution Allowlist", text)
            self.assertIn("public core seed", text)

        for path in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("clean-distribution-allowlist-core", text)
            self.assertIn("allowlist-built public distributions", text)


if __name__ == "__main__":
    unittest.main()

