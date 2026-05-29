#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_privileged_gui_job_runner_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test repeated privileged GUI job-runner contract validation.
Inputs: Workspace privileged GUI job-runner policy and local contract refs.
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

import privileged_gui_job_runner as pgr


class PrivilegedGuiJobRunnerPerformanceTests(unittest.TestCase):
    def test_privileged_gui_job_runner_validator_is_fast_enough_for_release_gate(self) -> None:
        result = pgr.benchmark_privileged_gui_job_runner(package_root=ROOT, iterations=80)

        self.assertTrue(result["ok"], result)
        self.assertEqual(0, result["failures"], result)
        self.assertLess(result["elapsed_seconds"], 5.0, result)
        self.assertGreater(result["iterations_per_second"], 5.0, result)


if __name__ == "__main__":
    unittest.main()
