#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_default_model_runtime_policy_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test the offline default model runtime policy validator.
Inputs: Workspace default model runtime policy and local contract refs.
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

import default_model_runtime_policy as dmrp


class DefaultModelRuntimePolicyPerformanceTests(unittest.TestCase):
    def test_default_model_runtime_validator_is_fast_enough_for_release_gate(self) -> None:
        result = dmrp.benchmark_default_model_runtime_policy(package_root=ROOT, iterations=80)

        self.assertTrue(result["ok"], result)
        self.assertEqual(0, result["failures"], result)
        self.assertLess(result["elapsed_seconds"], 5.0, result)
        self.assertGreater(result["iterations_per_second"], 5.0, result)


if __name__ == "__main__":
    unittest.main()
