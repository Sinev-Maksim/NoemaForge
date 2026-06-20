#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_editor_pack_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test docs coverage for Pipeline Editor pack draft edit/clone/review behavior.
Inputs: Workspace TODO, roadmap, changelog, release notes and pipeline-editor-pack policy.
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

import pipeline_editor_pack_runtime as pepr


class PipelineEditorPackQATests(unittest.TestCase):
    def test_policy_summary_and_docs_record_completed_pack_item(self) -> None:
        policy = pepr.load_policy(ROOT / "configs" / "pipeline-editor-pack-policy.json")
        report = pepr.validate_pipeline_editor_pack_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("pipeline-editor-pack-core", policy["id"])

        item = "Pipeline editor pack: drag-and-drop edit, clone as new pipeline class, Scary/Architecture/Admin review."
        _existing_docs = [p for p in [
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
            PROJECT_ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "TODO.md",
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"[x] {item}", text, str(path))
            self.assertIn("pipeline-editor-pack-core", text, str(path))
            self.assertIn("drag-and-drop edit, clone as new pipeline class, Scary/Architecture/Admin review", text, str(path))
            self.assertIn("draft-only", text, str(path))

    def test_changelog_release_notes_capture_pipeline_editor_contract(self) -> None:
        _existing_docs = [p for p in [
            PROJECT_ROOT / "CHANGELOG.md",
            PROJECT_ROOT / "RELEASE_NOTES.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("pipeline-editor-pack-core", text, str(path))
            self.assertIn("drag-and-drop edit, clone as new pipeline class, Scary/Architecture/Admin review", text, str(path))
            self.assertIn("draft-only", text, str(path))

    def test_full_drag_and_drop_ui_todo_remains_open_after_pack_contract(self) -> None:
        _existing_docs = [p for p in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("- [ ] Add full drag&drop pipeline editor implementation after alpha.", text, str(path))


if __name__ == "__main__":
    unittest.main()
