#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_canonical_model_eval_matrix_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Runtime-test the canonical CPU/GPU model evaluation matrix readiness contract.
Inputs: Canonical model eval matrix readiness policy and runtime validator.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import canonical_model_eval_matrix_readiness_runtime as cmr


class CanonicalModelEvalMatrixReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_matrix_execution(self) -> None:
        report = cmr.validate_canonical_model_eval_matrix_readiness_policy(cmr.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["matrix_readiness_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertEqual(summary["runtime_devices"], ["cpu", "gpu"])
        self.assertGreaterEqual(summary["required_dimension_count"], 8)
        self.assertIn("canonical_model_matrix_manifest", report)

    def test_missing_full_matrix_control_is_rejected(self) -> None:
        payload = cmr.load_policy()
        broken = copy.deepcopy(payload)
        broken["policy"]["required_safety_controls"]["full_matrix_required_before_completion"] = False
        failures = cmr._policy_failures(broken)
        self.assertIn("policy_safety_control_missing:full_matrix_required_before_completion", failures)

    def test_scorecard_dimensions_require_specific_runtime_devices(self) -> None:
        payload = cmr.load_policy()
        broken = copy.deepcopy(payload)
        for dimension in broken["policy"]["required_dimensions"]:
            if dimension["id"] == "gpu-scorecard-run":
                dimension["runtime_devices"] = ["cpu", "gpu"]
        failures = cmr._policy_failures(broken)
        self.assertIn("dimension_gpu_scorecard_runtime_device_invalid", failures)


if __name__ == "__main__":
    unittest.main()
