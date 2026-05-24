#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_task_workflow_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test the offline Admin task workflow validator.
Inputs: Workspace task-workflow policy and local source files.
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

import task_workflow_runtime as twr


class TaskWorkflowPerformanceTests(unittest.TestCase):
    def test_offline_task_workflow_validator_is_fast_enough_for_gui_regression_gate(self) -> None:
        result = twr.benchmark_task_workflow(package_root=ROOT, iterations=60)

        self.assertTrue(result["ok"], result)
        self.assertEqual(0, result["failures"], result)
        self.assertLess(result["elapsed_seconds"], 5.0, result)
        self.assertGreater(result["iterations_per_second"], 5.0, result)


if __name__ == "__main__":
    unittest.main()
