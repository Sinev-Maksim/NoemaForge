#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_firstboot_launcher_idempotency_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test firstboot launcher idempotency discoverability in source and docs.
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


class FirstbootLauncherIdempotencyQATests(unittest.TestCase):
    def test_source_exposes_launcher_lease_and_orchestrator_gate(self) -> None:
        status_source = (ROOT / "src" / "firstboot_status.py").read_text(encoding="utf-8")
        orchestrator_source = (ROOT / "src" / "firstboot_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn("acquire_run_lease", status_source)
        self.assertIn("release_run_lease", status_source)
        self.assertIn("firstboot-run.lock", status_source)
        self.assertIn("active_firstboot_run", status_source)
        self.assertIn("firstboot_already_running", orchestrator_source)
        self.assertLess(orchestrator_source.index("acquire_run_lease"), orchestrator_source.index("effective-first-start-options.json"))

    def test_todo_changelog_and_release_notes_record_completed_item(self) -> None:
        item = "Make launcher fully rerunnable and idempotent on target hardware."
        for path in [
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"[x] {item}", text, str(path))
            self.assertIn("firstboot-run.lock", text, str(path))

        for path in [
            PROJECT_ROOT / "CHANGELOG.md",
            PROJECT_ROOT / "RELEASE_NOTES.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("launcher rerun/idempotency", text, str(path))
            self.assertIn("firstboot-run.lock", text, str(path))


if __name__ == "__main__":
    unittest.main()
