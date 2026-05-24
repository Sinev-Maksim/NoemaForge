#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_performance_metrics_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Unit-test the offline pipeline performance metrics contract.
Inputs: Pipeline performance metrics policy and example metric artifacts.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import pipeline_performance_metrics_runtime as ppm


class PipelinePerformanceMetricsRuntimeTests(unittest.TestCase):
    def test_policy_validates_with_example_metrics(self) -> None:
        report = ppm.validate_pipeline_performance_metrics_policy(
            ppm.load_policy(),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
        )
        self.assertTrue(report["ok"], report["failures"])
        summary = report["pipeline_performance_metrics_summary"]
        self.assertEqual(3, summary["sample_count"])
        self.assertEqual(21.0, summary["max_latency_ms"])
        self.assertEqual(24.5, summary["max_memory_mb"])
        self.assertEqual(20, summary["total_operation_count"])
        self.assertEqual(14336, summary["total_artifact_bytes"])
        self.assertEqual({"passed": 2, "warn": 1}, summary["status_counts"])

    def test_summary_rejects_negative_and_non_integer_metrics(self) -> None:
        example = copy.deepcopy(ppm.load_example())
        example["samples"][0]["latency_ms"] = -1.0
        example["samples"][1]["operation_count"] = 2.5
        failures = ppm._example_failures(example, allowed_statuses={"passed", "warn", "failed", "skipped"})[
            "failures"
        ]
        self.assertIn("metric_non_negative_number_invalid:0:latency_ms", failures)
        self.assertIn("metric_non_negative_integer_invalid:1:operation_count", failures)

    def test_stage_ids_and_statuses_are_constrained(self) -> None:
        example = copy.deepcopy(ppm.load_example())
        example["samples"][0]["stage_id"] = "../unsafe"
        example["samples"][2]["status"] = "unknown"
        failures = ppm._example_failures(example, allowed_statuses={"passed", "warn", "failed", "skipped"})[
            "failures"
        ]
        self.assertIn("stage_id_invalid:0", failures)
        self.assertIn("metric_status_invalid:2:unknown", failures)


if __name__ == "__main__":
    unittest.main()
