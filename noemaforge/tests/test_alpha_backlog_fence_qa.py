#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_alpha_backlog_fence_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Alpha Backlog Fence discoverability through registry and canonical docs.
Inputs: Unified Registry, Alpha Backlog Fence policy and canonical documentation files.
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

import alpha_backlog_fence_runtime as abfr
import unified_registry_runtime as urr


class AlphaBacklogFenceQATests(unittest.TestCase):
    def test_alpha_backlog_fence_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:alpha-backlog-fence-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/alpha-backlog-fence.json", pack["refs"])
        self.assertIn("src/alpha_backlog_fence_runtime.py", pack["refs"])
        self.assertIn("tests/test_alpha_backlog_fence_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:alpha-backlog-fence-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/alpha-backlog-fence.json", pipeline["refs"])
        self.assertIn("src/alpha_backlog_fence_runtime.py", pipeline["refs"])

    def test_alpha_backlog_fence_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = abfr.load_policy(ROOT / "configs" / "alpha-backlog-fence.json")
        self.assertEqual("AlphaBacklogFencePolicy", policy["kind"])
        self.assertEqual("backlog_only", policy["policy"]["activation_state"])
        self.assertFalse(policy["policy"]["allow_auto_promotion"])

        report = abfr.validate_alpha_backlog_fence_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        _existing_docs = [p for p in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Keep this as backlog-only until alpha gates are stable.", text)
            self.assertIn("Alpha Backlog Fence", text)

        _existing_docs = [p for p in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("alpha-backlog-fence-core", text)
            self.assertIn("backlog-only promotion blocker", text)


if __name__ == "__main__":
    unittest.main()

