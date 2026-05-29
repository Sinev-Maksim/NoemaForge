#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_vault_reinventory_job_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Vault re-inventory job/fallback contract discoverability in canonical docs.
Inputs: Canonical TODO, roadmap, changelog and vault-reinventory-job policy.
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

import vault_reinventory_job_runtime as vrj


class VaultReinventoryJobQATests(unittest.TestCase):
    def test_policy_summary_and_docs_record_completed_item(self) -> None:
        policy = vrj.load_policy(ROOT / "configs" / "vault-reinventory-job-policy.json")
        report = vrj.validate_vault_reinventory_job_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("vault-reinventory-job-core", policy["id"])

        item = "Verify `Re-inventory Vault` returns a privileged job/fallback command instead of a silent failure."
        for path in [
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"[x] {item}", text, str(path))
            self.assertIn("vault-reinventory-job-core", text, str(path))

    def test_changelog_release_notes_capture_vault_reinventory_job(self) -> None:
        for path in [
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Vault re-inventory", text, str(path))
            self.assertIn("fallback command", text, str(path))
            self.assertIn("needs_privilege", text, str(path))


if __name__ == "__main__":
    unittest.main()
