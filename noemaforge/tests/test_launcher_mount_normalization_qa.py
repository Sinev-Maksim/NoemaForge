#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_launcher_mount_normalization_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test launcher mount normalization discoverability in docs and backlog.
Inputs: Firstboot runtime source and canonical documentation files.
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


class LauncherMountNormalizationQATests(unittest.TestCase):
    def test_runtime_and_docs_capture_launcher_mount_normalization(self) -> None:
        runtime = (ROOT / "src" / "firstboot_orchestrator.py").read_text(encoding="utf-8")
        safety = (ROOT / "src" / "runtime_safety.py").read_text(encoding="utf-8")
        self.assertIn("normalize_launcher_paths", runtime)
        self.assertIn("path_normalization", runtime)
        self.assertIn("canonicalize_noemaforge_path", safety)

        expected = "[x] Implement mount normalization to `/mnt/noemaforge-share` in the launcher happy path."
        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            self.assertIn(expected, path.read_text(encoding="utf-8"))

        for path in [
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
            PROJECT_ROOT / "RELEASE_NOTES.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("launcher mount normalization", text)
            self.assertIn("/mnt/noemaforge-share", text)


if __name__ == "__main__":
    unittest.main()
