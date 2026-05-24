#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_first_start_abort_recovery_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test first-start abort recovery regression discoverability in docs and release notes.
Inputs: Workspace TODO, changelog, release notes and first-start-abort-recovery policy.
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

import first_start_abort_recovery_runtime as fsar


class FirstStartAbortRecoveryQATests(unittest.TestCase):
    def test_policy_summary_and_docs_record_completed_item(self) -> None:
        policy = fsar.load_policy(ROOT / "configs" / "first-start-abort-recovery-policy.json")
        report = fsar.validate_first_start_abort_recovery_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertIn("--dry-run", policy["policy"]["required_cli_tokens"])

        item = "Add automated regression for `noemaforge first-start abort` non-blocking GUI recovery."
        for path in [
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"[x] {item}", text, str(path))
            self.assertIn("first-start-abort-recovery-core", text, str(path))

    def test_changelog_release_notes_capture_abort_recovery(self) -> None:
        for path in [
            PROJECT_ROOT / "CHANGELOG.md",
            PROJECT_ROOT / "RELEASE_NOTES.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("first-start abort recovery", text, str(path))
            self.assertIn("--dry-run", text, str(path))
            self.assertIn("non-blocking GUI recovery", text, str(path))


if __name__ == "__main__":
    unittest.main()
