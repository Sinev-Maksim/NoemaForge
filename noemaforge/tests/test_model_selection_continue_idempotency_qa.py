#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_model_selection_continue_idempotency_qa.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Continue model selection idempotency discoverability in canonical docs.
Inputs: Canonical TODO, roadmap, changelog and model-selection-continue-idempotency policy.
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

import model_selection_continue_idempotency_runtime as msci


class ModelSelectionContinueIdempotencyQATests(unittest.TestCase):
    def test_policy_summary_and_docs_record_completed_item(self) -> None:
        policy = msci.load_policy(ROOT / "configs" / "model-selection-continue-idempotency-policy.json")
        report = msci.validate_model_selection_continue_idempotency_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("model-selection-continue-idempotency-core", policy["id"])

        item = "Verify `Continue model selection` uses job/idempotency state and does not duplicate active selection work after page refresh."
        for path in [
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"[x] {item}", text, str(path))
            self.assertIn("model-selection-continue-idempotency-core", text, str(path))

    def test_changelog_release_notes_capture_continue_idempotency(self) -> None:
        for path in [
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Continue model selection", text, str(path))
            self.assertIn("idempotency", text, str(path))
            self.assertIn("needs_privilege", text, str(path))


if __name__ == "__main__":
    unittest.main()
