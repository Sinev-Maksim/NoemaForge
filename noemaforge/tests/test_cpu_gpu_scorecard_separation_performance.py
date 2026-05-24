#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_cpu_gpu_scorecard_separation_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test the offline CPU/GPU scorecard separation validator.
Inputs: Workspace CPU/GPU scorecard separation policy and local refs.
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

import cpu_gpu_scorecard_separation_runtime as cgs


class CpuGpuScorecardSeparationPerformanceTests(unittest.TestCase):
    def test_scorecard_separation_validator_is_fast_enough_for_release_gate(self) -> None:
        result = cgs.benchmark_cpu_gpu_scorecard_separation(package_root=ROOT, iterations=120)

        self.assertTrue(result["ok"], result)
        self.assertEqual(0, result["failures"], result)
        self.assertLess(result["elapsed_seconds"], 5.0, result)
        self.assertGreater(result["iterations_per_second"], 10.0, result)


if __name__ == "__main__":
    unittest.main()
