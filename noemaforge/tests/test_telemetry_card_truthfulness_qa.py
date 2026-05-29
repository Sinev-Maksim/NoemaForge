#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_telemetry_card_truthfulness_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test docs coverage for telemetry card truthfulness.
Inputs: Workspace TODO, roadmap, changelog, release notes and telemetry-card-truthfulness policy.
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

import telemetry_card_truthfulness_runtime as tct


class TelemetryCardTruthfulnessQATests(unittest.TestCase):
    def test_policy_summary_and_docs_record_completed_item(self) -> None:
        policy = tct.load_policy(ROOT / "configs" / "telemetry-card-truthfulness-policy.json")
        report = tct.validate_telemetry_card_truthfulness_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("telemetry-card-truthfulness-core", policy["id"])

        item = "Verify telemetry cards show hardware, runtime and product metrics without overstating creative-media quality."
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
            self.assertIn("telemetry-card-truthfulness-core", text, str(path))
            self.assertIn("review-required creative-media policy", text, str(path))

    def test_changelog_release_notes_capture_telemetry_truthfulness(self) -> None:
        for path in [
            PROJECT_ROOT / "CHANGELOG.md",
            PROJECT_ROOT / "RELEASE_NOTES.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("telemetry-card-truthfulness-core", text, str(path))
            self.assertIn("telemetry cards show hardware, runtime and product metrics without overstating creative-media quality", text, str(path))
            self.assertIn("review-required creative-media policy", text, str(path))


if __name__ == "__main__":
    unittest.main()
