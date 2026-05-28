#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_telemetry_card_truthfulness_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate telemetry card sections and creative-media quality truthfulness.
Inputs: Workspace telemetry-card-truthfulness policy and Admin GUI server runtime.
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


class TelemetryCardTruthfulnessRuntimeTests(unittest.TestCase):
    def test_workspace_telemetry_card_truthfulness_validates(self) -> None:
        policy_path = ROOT / "configs" / "telemetry-card-truthfulness-policy.json"
        report = tct.validate_telemetry_card_truthfulness_policy(
            tct.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(3, report["metrics"]["source_reports"])
        self.assertEqual(3, report["metrics"]["valid_source_reports"])
        self.assertGreater(report["metrics"]["telemetry_block_chars"], 100)

    def test_telemetry_fixture_contains_hardware_runtime_product_sections(self) -> None:
        telemetry = tct.build_telemetry_status_fixture(package_root=ROOT)

        self.assertTrue(telemetry["ok"], telemetry)
        self.assertIn("hardware", telemetry)
        self.assertIn("runtime", telemetry)
        self.assertIn("product", telemetry)
        self.assertIn("memory", telemetry["hardware"])
        self.assertIn("model_selection", telemetry["product"])

    def test_creative_media_quality_is_review_required_not_overclaimed(self) -> None:
        telemetry = tct.build_telemetry_status_fixture(package_root=ROOT)
        creative = telemetry["product"]["creative_media"]

        self.assertEqual("not_measured_without_explicit_evaluator", creative["quality_evaluation_state"])
        self.assertEqual("metadata_and_review_required", creative["quality_claim_policy"])
        self.assertIn("quality is not claimed", creative["note"])
        self.assertIn("review-required", telemetry["creative_metrics_policy"])


if __name__ == "__main__":
    unittest.main()
