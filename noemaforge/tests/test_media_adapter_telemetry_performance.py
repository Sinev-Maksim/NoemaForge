#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_media_adapter_telemetry_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test bounded media adapter telemetry evaluation.
Inputs: Workspace media adapter telemetry policy and synthetic telemetry samples.
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
sys.path.insert(0, str(ROOT / "src"))

import media_adapter_telemetry_runtime as matr


class MediaAdapterTelemetryPerformanceTests(unittest.TestCase):
    def test_synthetic_adapter_telemetry_batch_runs_under_budget(self) -> None:
        policy = matr.load_policy(ROOT / "configs" / "media-adapter-telemetry-policy.json")
        result = matr.benchmark_media_adapter_telemetry(policy, iterations=1200)

        self.assertTrue(result["ok"], result)
        self.assertEqual(1200, result["passed"])
        self.assertEqual(0, result["failed"])
        self.assertLess(result["elapsed_sec"], 2.0)


if __name__ == "__main__":
    unittest.main()
