#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_machine_local_defaults_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test machine-local default discoverability in docs and changelog.
Inputs: Workspace policy, TODO, changelog and policy example files.
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

import machine_local_defaults_runtime as mldr


class MachineLocalDefaultsQATests(unittest.TestCase):
    def test_policy_example_copies_are_identical_and_non_secret(self) -> None:
        policy = mldr.load_policy(ROOT / "configs" / "machine-local-defaults-policy.json")
        report = mldr.validate_machine_local_defaults_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for item in report["defaults"]:
            source = Path(item["resolved"]["source"]["path"]).read_text(encoding="utf-8")
            docs = Path(item["resolved"]["docs"]["path"]).read_text(encoding="utf-8")
            package_docs = Path(item["resolved"]["package_docs"]["path"]).read_text(encoding="utf-8")
            self.assertEqual(source, docs, item["name"])
            self.assertEqual(source, package_docs, item["name"])
            self.assertNotIn("PASSWORD=", source)
            self.assertNotIn("SECRET=", source)
            self.assertNotIn("TOKEN=", source)

    def test_todo_changelog_and_release_notes_record_completed_item(self) -> None:
        item = "Finalize `/etc/default/noemaforge-*` defaults for machine-local overrides."
        for path in [p for p in [
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ] if p.exists()]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"[x] {item}", text, str(path))
            self.assertIn("machine-local-defaults-core", text, str(path))

        for path in [p for p in [
            PROJECT_ROOT / "CHANGELOG.md",
            PROJECT_ROOT / "RELEASE_NOTES.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ] if p.exists()]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("machine-local defaults", text, str(path))
            self.assertIn("noemaforge-runtime.example", text, str(path))
            self.assertIn("noemaforge-firstboot.example", text, str(path))


if __name__ == "__main__":
    unittest.main()
