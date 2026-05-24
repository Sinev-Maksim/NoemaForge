#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_stateful_admin_gui_qa.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test docs coverage for stateful Admin GUI install validation.
Inputs: Workspace TODO, roadmap, changelog, release notes and stateful-admin-gui policy.
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

import stateful_admin_gui_runtime as sagr


class StatefulAdminGuiQATests(unittest.TestCase):
    def test_policy_summary_and_docs_record_completed_item(self) -> None:
        policy = sagr.load_policy(ROOT / "configs" / "stateful-admin-gui-policy.json")
        report = sagr.validate_stateful_admin_gui_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("stateful-admin-gui-core", policy["id"])

        item = "Validate stateful Admin GUI after installation: conversation restore, persona portrait, task queue, job panel, telemetry and pipeline dock."
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
            self.assertIn("stateful-admin-gui-core", text, str(path))
            self.assertIn("conversation restore, persona portrait, task queue, job panel, telemetry and pipeline dock", text, str(path))

    def test_changelog_release_notes_capture_stateful_gui_contract(self) -> None:
        for path in [
            PROJECT_ROOT / "CHANGELOG.md",
            PROJECT_ROOT / "RELEASE_NOTES.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("stateful-admin-gui-core", text, str(path))
            self.assertIn("stateful Admin GUI", text, str(path))
            self.assertIn("conversation restore", text, str(path))
            self.assertIn("persona portrait", text, str(path))
            self.assertIn("pipeline dock", text, str(path))


if __name__ == "__main__":
    unittest.main()
