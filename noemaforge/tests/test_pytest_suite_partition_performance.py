#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pytest_suite_partition_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test bounded pytest shard planning on synthetic test lists.
Inputs: Synthetic test file paths.
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
sys.path.insert(0, str(ROOT / "src"))

import pytest_suite_partition_runtime as pspr


class PytestSuitePartitionPerformanceTests(unittest.TestCase):
    def test_partition_planning_stays_bounded_for_many_tests(self) -> None:
        policy = pspr.load_policy(ROOT / "configs" / "pytest-suite-partition-policy.json")
        tests = []
        for index in range(2500):
            if index % 5 == 0:
                tests.append(f"noemaforge/tests/test_pipeline_runtime_synthetic_{index:04d}.py")
            else:
                tests.append(f"noemaforge/tests/test_general_contract_synthetic_{index:04d}.py")

        started = time.perf_counter()
        plan = pspr.partition_tests(tests, policy=policy)
        validation = pspr.validate_partition_plan(plan, policy=policy)
        elapsed = time.perf_counter() - started

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(2500, plan["metrics"]["test_count"])
        self.assertGreater(plan["metrics"]["pipeline_runtime_shards"], 0)
        self.assertLess(elapsed, 0.75, f"pytest suite partition planning took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
