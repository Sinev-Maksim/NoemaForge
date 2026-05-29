#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_dev_bounded_loop_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test docs coverage for bounded Dev Team loop checkpoint/stop behavior.
Inputs: Workspace TODO, roadmap, changelog, release notes and dev-bounded-loop policy.
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

import dev_bounded_loop_runtime as dblp


class DevBoundedLoopQATests(unittest.TestCase):
    def test_policy_summary_and_docs_record_completed_item(self) -> None:
        policy = dblp.load_policy(ROOT / "configs" / "dev-bounded-loop-policy.json")
        report = dblp.validate_dev_bounded_loop_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("dev-bounded-loop-core", policy["id"])

        item = "Extend bounded-improvement depth to real multi-step Dev Team loops with checkpoint/stop handling."
        for path in [
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
            PROJECT_ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "TODO.md",
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"[x] {item}", text, str(path))
            self.assertIn("dev-bounded-loop-core", text, str(path))
            self.assertIn("checkpoint/stop handling", text, str(path))
            self.assertIn("never auto-apply", text, str(path))

    def test_changelog_release_notes_capture_bounded_loop_policy(self) -> None:
        for path in [
            PROJECT_ROOT / "CHANGELOG.md",
            PROJECT_ROOT / "RELEASE_NOTES.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("dev-bounded-loop-core", text, str(path))
            self.assertIn("checkpoint/stop handling", text, str(path))
            self.assertIn("never auto-apply", text, str(path))


if __name__ == "__main__":
    unittest.main()
