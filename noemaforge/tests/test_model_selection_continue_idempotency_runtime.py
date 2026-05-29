#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_model_selection_continue_idempotency_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate GUI Continue model selection idempotency across refresh/retry.
Inputs: Workspace model-selection-continue-idempotency policy and Admin GUI server runtime.
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


class ModelSelectionContinueIdempotencyRuntimeTests(unittest.TestCase):
    def test_workspace_model_selection_continue_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "model-selection-continue-idempotency-policy.json"
        report = msci.validate_model_selection_continue_idempotency_policy(
            msci.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["script_reports"])
        self.assertEqual(1, report["metrics"]["valid_script_reports"])
        self.assertEqual(1, report["metrics"]["matching_job_count"])

    def test_continue_returns_same_job_after_refresh_retry(self) -> None:
        sequence = msci.build_continue_idempotency_sequence(package_root=ROOT)

        self.assertTrue(sequence["first"]["ok"], sequence)
        self.assertTrue(sequence["second"]["ok"], sequence)
        self.assertTrue(sequence["same_job"], sequence)
        self.assertEqual(1, sequence["matching_job_count"], sequence)
        self.assertEqual(sequence["first"]["job"]["job_id"], sequence["second"]["job"]["job_id"])
        self.assertEqual(1, len(sequence["final_jobs"]["jobs"]), sequence)

    def test_persisted_job_keeps_safe_command_artifact_and_display_policy(self) -> None:
        sequence = msci.build_continue_idempotency_sequence(package_root=ROOT)
        job = sequence["final_jobs"]["jobs"][0]

        self.assertEqual("needs_privilege", job["status"])
        self.assertEqual("model-selection-continue:full_composite:4", job["idempotency_key"])
        self.assertEqual("preserve_display_manager", job["display_policy"])
        self.assertIn("--dry-run", job["safe_command"])
        self.assertIn("--keep-display", job["safe_command"])
        self.assertIn("--show-candidates", job["safe_command"])
        self.assertIn("real_command_requires_operator_terminal", job)
        self.assertTrue(any(item["type"] == "model_selection_continue" for item in job["artifacts"]))


if __name__ == "__main__":
    unittest.main()
