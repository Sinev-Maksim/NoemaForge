#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_firstboot_attempt_archive_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test firstboot attempt archive discoverability in source and docs.
Inputs: Workspace source, TODO, changelog and release-note files.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent


class FirstbootAttemptArchiveQATests(unittest.TestCase):
    def test_source_exposes_archive_contract(self) -> None:
        source = (ROOT / "src" / "firstboot_status.py").read_text(encoding="utf-8")
        self.assertIn("archive_previous_attempt", source)
        self.assertIn("firstboot-attempt-archive", source)
        self.assertIn("noemaforge.firstbootattemptarchive/v1", source)
        self.assertIn("previous_attempt_archive", source)
        self.assertIn("interrupted_state_", source)

    def test_todo_changelog_and_release_notes_record_completed_item(self) -> None:
        item = "Add automatic archival of failed/invalid firstboot attempts."
        for path in [
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"[x] {item}", text, str(path))
            self.assertIn("firstboot-attempt-archive", text, str(path))

        for path in [
            PROJECT_ROOT / "CHANGELOG.md",
            PROJECT_ROOT / "RELEASE_NOTES.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("failed/invalid firstboot", text, str(path))
            self.assertIn("firstboot-attempt-archive", text, str(path))


if __name__ == "__main__":
    unittest.main()
