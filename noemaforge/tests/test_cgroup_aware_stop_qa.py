#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_cgroup_aware_stop_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test cgroup-aware stop/reboot-safe discoverability in docs and changelog.
Inputs: Workspace TODO, changelog, release notes and cgroup-aware-stop policy.
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

import cgroup_aware_stop_runtime as casr


class CgroupAwareStopQATests(unittest.TestCase):
    def test_policy_summary_and_docs_record_completed_item(self) -> None:
        policy = casr.load_policy(ROOT / "configs" / "cgroup-aware-stop-policy.json")
        report = casr.validate_cgroup_aware_stop_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertIn("cgroup_proc_drain", policy["policy"]["required_outputs"])

        item = "Make stop/reboot-safe fully cgroup-aware."
        _existing_docs = [p for p in [
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"[x] {item}", text, str(path))
            self.assertIn("cgroup-aware-stop-core", text, str(path))

    def test_changelog_release_notes_capture_cgroup_aware_stop(self) -> None:
        _existing_docs = [p for p in [
            PROJECT_ROOT / "CHANGELOG.md",
            PROJECT_ROOT / "RELEASE_NOTES.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("cgroup-aware stop", text, str(path))
            self.assertIn("ControlGroup", text, str(path))
            self.assertIn("cgroup.procs", text, str(path))


if __name__ == "__main__":
    unittest.main()
