#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_premerge_release_guard_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test pre-merge release guard discoverability through registry and docs.
Inputs: Unified Registry, pre-merge release guard policy and canonical documentation files.
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

import premerge_release_guard_runtime as prgr
import unified_registry_runtime as urr


class PremergeReleaseGuardQATests(unittest.TestCase):
    def test_premerge_release_guard_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:premerge-release-guard-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/premerge-release-guard-policy.json", pack["refs"])
        self.assertIn("contracts/premerge_release_guard.schema.json", pack["refs"])
        self.assertIn("src/selftest_runtime.py", pack["refs"])
        self.assertIn("src/premerge_release_guard_runtime.py", pack["refs"])
        self.assertIn("tests/test_premerge_release_guard_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:premerge-release-guard-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/premerge-release-guard-policy.json", pipeline["refs"])
        self.assertIn("src/premerge_release_guard_runtime.py", pipeline["refs"])

    def test_premerge_release_guard_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = prgr.load_policy(ROOT / "configs" / "premerge-release-guard-policy.json")
        self.assertEqual("PremergeReleaseGuardPolicy", policy["kind"])
        self.assertEqual("premerge_release_guard", policy["policy"]["activation_state"])
        self.assertIn("release-guard", policy["policy"]["required_selftest_commands"])

        validation = prgr.validate_premerge_release_guard_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(validation["ok"], validation["failures"])

        _existing_docs = [p for p in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Promote regression gate into pre-merge release guard for 0.31.x.", text)
            self.assertIn("premerge-release-guard-core", text)

        _existing_docs = [p for p in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("premerge-release-guard-core", text)
            self.assertIn("noemaforge selftest release-guard", text)


if __name__ == "__main__":
    unittest.main()

