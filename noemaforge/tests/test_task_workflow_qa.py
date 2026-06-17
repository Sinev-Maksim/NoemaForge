#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_task_workflow_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test docs coverage for Admin task workflow through chat and API.
Inputs: Workspace TODO, roadmap, changelog, release notes and task-workflow policy.
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

import task_workflow_runtime as twr


class TaskWorkflowQATests(unittest.TestCase):
    def test_policy_summary_and_docs_record_completed_item(self) -> None:
        policy = twr.load_policy(ROOT / "configs" / "task-workflow-policy.json")
        report = twr.validate_task_workflow_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("task-workflow-core", policy["id"])

        item = "Verify task add/edit/prioritize/block/complete through Admin chat and API."
        for path in [p for p in [
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
            PROJECT_ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "TODO.md",
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ] if p.exists()]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"[x] {item}", text, str(path))
            self.assertIn("task-workflow-core", text, str(path))
            self.assertIn("Admin chat and API", text, str(path))

    def test_changelog_release_notes_capture_task_workflow(self) -> None:
        for path in [p for p in [
            PROJECT_ROOT / "CHANGELOG.md",
            PROJECT_ROOT / "RELEASE_NOTES.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ] if p.exists()]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("task-workflow-core", text, str(path))
            self.assertIn("task add/edit/prioritize/block/complete", text, str(path))
            self.assertIn("Admin chat and API", text, str(path))


if __name__ == "__main__":
    unittest.main()
