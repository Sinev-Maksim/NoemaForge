#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_performance_metrics_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Bounded regression test for pipeline performance metrics validation.
Inputs: Pipeline performance metrics policy and example metric artifacts.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import pipeline_performance_metrics_runtime as ppm


class PipelinePerformanceMetricsPerformanceTests(unittest.TestCase):
    def test_metric_summary_stays_bounded(self) -> None:
        samples = ppm.load_example()["samples"] * 100
        started = time.perf_counter()
        summaries = [ppm.summarize_metric_samples(samples) for _ in range(100)]
        elapsed = time.perf_counter() - started
        self.assertEqual(300, summaries[-1]["sample_count"])
        self.assertEqual(2000, summaries[-1]["total_operation_count"])
        self.assertLess(elapsed, 0.25)

    def test_policy_validation_stays_bounded(self) -> None:
        policy = ppm.load_policy()
        started = time.perf_counter()
        reports = [
            ppm.validate_pipeline_performance_metrics_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
            for _ in range(20)
        ]
        elapsed = time.perf_counter() - started
        self.assertTrue(all(item["ok"] for item in reports), reports[-1]["failures"])
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
