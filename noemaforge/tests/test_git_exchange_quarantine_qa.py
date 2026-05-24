#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_git_exchange_quarantine_qa.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test git_exchange discoverability through registry and canonical docs.
Inputs: Unified Registry, git_exchange policy and canonical documentation files.
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

import git_exchange_quarantine_runtime as geqr
import unified_registry_runtime as urr


class GitExchangeQuarantineQATests(unittest.TestCase):
    def test_git_exchange_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:git-exchange-quarantine-core:0.32.0")
        self.assertIsNotNone(pack)
        self.assertIn("configs/git-exchange-quarantine-policy.json", pack["refs"])
        self.assertIn("src/git_exchange_quarantine_runtime.py", pack["refs"])
        self.assertIn("tests/test_git_exchange_quarantine_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.31.13.alpha-patched1"]
        self.assertIn("eval-pack:git-exchange-quarantine-core:0.32.0", pipeline["eval_pack_refs"])
        self.assertIn("configs/git-exchange-quarantine-policy.json", pipeline["refs"])
        self.assertIn("src/git_exchange_quarantine_runtime.py", pipeline["refs"])

    def test_git_exchange_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = geqr.load_policy(ROOT / "configs" / "git-exchange-quarantine-policy.json")
        self.assertEqual("GitExchangePolicy", policy["kind"])
        self.assertEqual("quarantine_first", policy["policy"]["activation_state"])
        self.assertIn("ModelDeltaPack", policy["policy"]["allowed_pack_kinds"])

        report = geqr.validate_git_exchange_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Add quarantine-first `git_exchange`", text)
            self.assertIn("Git Exchange Quarantine", text)
            self.assertIn("ModelDeltaPack", text)

        text = (ROOT / "docs" / "history" / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("git-exchange-quarantine-core", text)
        self.assertIn("quarantine-first", text)

    def test_git_exchange_pack_roadmap_item_is_closed_in_canonical_docs(self) -> None:
        closure = (
            "[x] Git exchange pack: quarantine-first RolePack, RoleFlow, EvalPack and "
            "KnowledgeGraphPack import/export. Closed by `git-exchange-quarantine-core`"
        )
        for path in [
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(closure, text)
            self.assertNotIn(
                "[ ] Git exchange pack: quarantine-first RolePack, RoleFlow, EvalPack and KnowledgeGraphPack import/export.",
                text,
            )

        changelog = (ROOT / "docs" / "history" / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("Git exchange pack: quarantine-first RolePack, RoleFlow, EvalPack and KnowledgeGraphPack import/export", changelog)
        self.assertIn("git-exchange-quarantine-core", changelog)


if __name__ == "__main__":
    unittest.main()

