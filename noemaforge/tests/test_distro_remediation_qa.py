#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_distro_remediation_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test distro remediation discoverability in docs and release notes.
Inputs: Workspace TODO, changelog, release notes and distro-remediation policy.
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

import distro_remediation_runtime as drr


class DistroRemediationQATests(unittest.TestCase):
    def test_policy_summary_and_docs_record_completed_item(self) -> None:
        policy = drr.load_policy(ROOT / "configs" / "distro-remediation-policy.json")
        report = drr.validate_distro_remediation_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertIn("fedora", policy["policy"]["supported_families"])
        self.assertIn("--apply-remediation", policy["policy"]["required_preflight_flags"])

        item = "Add distro detection and missing dependency remediation, not only detection."
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
            self.assertIn("distro-remediation-core", text, str(path))

    def test_changelog_release_notes_capture_distro_remediation(self) -> None:
        _existing_docs = [p for p in [
            PROJECT_ROOT / "CHANGELOG.md",
            PROJECT_ROOT / "RELEASE_NOTES.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("distro remediation", text, str(path))
            self.assertIn("--remediation-plan", text, str(path))
            self.assertIn("NOEMAFORGE_ALLOW_PACKAGE_REMEDIATION", text, str(path))


if __name__ == "__main__":
    unittest.main()
