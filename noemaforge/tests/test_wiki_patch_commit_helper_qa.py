#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_wiki_patch_commit_helper_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test reviewed wiki-patch commit-helper discoverability through registry and docs.
Inputs: Unified Registry, commit-helper policy and canonical documentation files.
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

import unified_registry_runtime as urr
import wiki_patch_commit_helper_runtime as wpchr


class WikiPatchCommitHelperQATests(unittest.TestCase):
    def test_wiki_patch_commit_helper_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:wiki-patch-commit-helper-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/wiki-patch-commit-helper-policy.json", pack["refs"])
        self.assertIn("contracts/wiki_patch_commit_helper.schema.json", pack["refs"])
        self.assertIn("src/selftest_runtime.py", pack["refs"])
        self.assertIn("src/wiki_patch_commit_helper_runtime.py", pack["refs"])
        self.assertIn("tests/test_wiki_patch_commit_helper_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:wiki-patch-commit-helper-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/wiki-patch-commit-helper-policy.json", pipeline["refs"])
        self.assertIn("src/wiki_patch_commit_helper_runtime.py", pipeline["refs"])

    def test_wiki_patch_commit_helper_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = wpchr.load_policy(ROOT / "configs" / "wiki-patch-commit-helper-policy.json")
        self.assertEqual("WikiPatchCommitHelperPolicy", policy["kind"])
        self.assertEqual("reviewed_wiki_patch_commit_plan", policy["policy"]["activation_state"])
        self.assertIn("commit-plan", policy["policy"]["required_wiki_patch_commands"])

        validation = wpchr.validate_wiki_patch_commit_helper_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(validation["ok"], validation["failures"])

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Add automatic wiki repo branch/commit helper after operator review in 0.31.x.", text)
            self.assertIn("wiki-patch-commit-helper-core", text)

        for path in [
            PROJECT_ROOT / "docs" / "README.md",
            ROOT / "docs" / "README.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("wiki-patch-commit-helper-core", text)
            self.assertIn("noemaforge wiki-patch commit-plan", text)


if __name__ == "__main__":
    unittest.main()

