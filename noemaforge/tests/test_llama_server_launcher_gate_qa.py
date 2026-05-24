#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_llama_server_launcher_gate_qa.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test llama-server launcher gate discoverability in docs and release notes.
Inputs: Workspace TODO, changelog, release notes and llama-server-launcher-gate policy.
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

import llama_server_launcher_gate_runtime as lsg


class LlamaServerLauncherGateQATests(unittest.TestCase):
    def test_policy_summary_and_docs_record_completed_item(self) -> None:
        policy = lsg.load_policy(ROOT / "configs" / "llama-server-launcher-gate-policy.json")
        report = lsg.validate_llama_server_launcher_gate_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertIn("llama_libs", policy["policy"]["required_preflight_checks"])

        item = "Add `llama-server` binary/shared-library preflight"
        for path in [
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(item, text, str(path))
            self.assertIn("llama-server-launcher-gate-core", text, str(path))

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Add `llama-server` binary/shared-library preflight", text, str(path))

    def test_changelog_release_notes_capture_launcher_gate(self) -> None:
        for path in [
            PROJECT_ROOT / "CHANGELOG.md",
            PROJECT_ROOT / "RELEASE_NOTES.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("llama-server launcher gate", text, str(path))
            self.assertIn("unresolved shared libraries", text, str(path))
            self.assertIn("validate_llama_server_runtime", text, str(path))


if __name__ == "__main__":
    unittest.main()
