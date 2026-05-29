#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_target_gui_recovery_path_readiness_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Bounded regression-test target GUI recovery path readiness validation runtime.
Inputs: Target GUI recovery path readiness policy and example fixtures.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import target_gui_recovery_path_readiness_runtime as tgr


class TargetGuiRecoveryPathReadinessPerformanceTests(unittest.TestCase):
    def test_policy_validation_is_bounded_for_small_fixture(self) -> None:
        payload = tgr.load_policy()
        started = time.perf_counter()
        for _ in range(25):
            report = tgr.validate_target_gui_recovery_path_readiness_policy(payload)
            self.assertTrue(report["ok"], report["failures"])
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
