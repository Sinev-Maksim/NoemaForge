#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_media_adapter_telemetry_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate media adapter telemetry runtime behaviour.
Inputs: Workspace media adapter telemetry policy and examples.
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

import media_adapter_telemetry_runtime as matr


class MediaAdapterTelemetryRuntimeTests(unittest.TestCase):
    def test_workspace_media_adapter_telemetry_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "media-adapter-telemetry-policy.json"
        report = matr.validate_media_adapter_telemetry_policy(
            matr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(6, report["metrics"]["adapters"])
        self.assertEqual(18, report["metrics"]["selftest_case_slots"])
        self.assertEqual(6, report["metrics"]["example_adapters"])

    def test_plan_only_smoke_records_required_metrics_without_live_backend(self) -> None:
        policy = matr.load_policy(ROOT / "configs" / "media-adapter-telemetry-policy.json")
        result = matr.evaluate_adapter_selftest_case("music_generation", "plan_only_smoke", policy)

        self.assertTrue(result["ok"], result["failures"])
        self.assertFalse(result["live_backend_started"])
        self.assertEqual("music_generation", result["adapter"])
        for metric in matr.REQUIRED_METRICS:
            self.assertIn(metric, result["metrics"])

    def test_unknown_adapter_sample_is_rejected(self) -> None:
        policy = matr.load_policy(ROOT / "configs" / "media-adapter-telemetry-policy.json")
        sample = matr.synthetic_telemetry_sample("unknown_media", "plan_only_smoke")
        result = matr.validate_telemetry_sample(sample, policy)

        self.assertFalse(result["ok"])
        self.assertIn("unknown_adapter", result["failures"])


if __name__ == "__main__":
    unittest.main()
