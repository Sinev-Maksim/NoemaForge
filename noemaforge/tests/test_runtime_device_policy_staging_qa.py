#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_runtime_device_policy_staging_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test docs coverage for CPU/GPU staged runtime device policy.
Inputs: Workspace TODO, roadmap, changelog, release notes and runtime-device-policy-staging policy.
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

import runtime_device_policy_staging_runtime as rdps


class RuntimeDevicePolicyStagingQATests(unittest.TestCase):
    def test_policy_summary_and_docs_record_completed_item(self) -> None:
        policy = rdps.load_policy(ROOT / "configs" / "runtime-device-policy-staging-policy.json")
        report = rdps.validate_runtime_device_policy_staging_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("runtime-device-policy-staging-core", policy["id"])

        item = "Verify CPU/GPU staged policy applies only on next persona/model switch or backend restart."
        for path in [
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"[x] {item}", text, str(path))
            self.assertIn("runtime-device-policy-staging-core", text, str(path))
            self.assertIn("next persona/model switch or backend restart", text, str(path))

    def test_changelog_release_notes_capture_staged_device_policy(self) -> None:
        for path in [
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("runtime-device-policy-staging-core", text, str(path))
            self.assertIn("CPU/GPU staged policy", text, str(path))
            self.assertIn("next persona/model switch or backend restart", text, str(path))


if __name__ == "__main__":
    unittest.main()
