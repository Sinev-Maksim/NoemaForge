#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_model_route_distinction_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test documentation coverage for Model Selection vs Model Evolution distinction.
Inputs: Workspace TODO, roadmap, changelog, release notes and model-route-distinction policy.
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

import model_route_distinction_runtime as mrdr


class ModelRouteDistinctionQATests(unittest.TestCase):
    def test_policy_summary_and_docs_record_completed_item(self) -> None:
        policy = mrdr.load_policy(ROOT / "configs" / "model-route-distinction-policy.json")
        report = mrdr.validate_model_route_distinction_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("model-route-distinction-core", policy["id"])

        item = "Verify Model Selection and Model Evolution routing are visually and semantically distinct."
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
            self.assertIn("model-route-distinction-core", text, str(path))
            self.assertIn("Model Selection", text, str(path))
            self.assertIn("Model Evolution", text, str(path))

    def test_changelog_release_notes_capture_route_distinction(self) -> None:
        for path in [
            PROJECT_ROOT / "CHANGELOG.md",
            PROJECT_ROOT / "RELEASE_NOTES.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("model-route-distinction-core", text, str(path))
            self.assertIn("Model Selection", text, str(path))
            self.assertIn("Model Evolution", text, str(path))
            self.assertIn("visually and semantically distinct", text, str(path))


if __name__ == "__main__":
    unittest.main()
