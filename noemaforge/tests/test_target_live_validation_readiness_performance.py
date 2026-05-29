#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_target_live_validation_readiness_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Keep target live validation readiness checks bounded for local CI.
Inputs: Target live validation readiness policy and runtime validator.
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

import target_live_validation_readiness_runtime as tlv


class TargetLiveValidationReadinessPerformanceTests(unittest.TestCase):
    def test_readiness_validation_stays_bounded(self) -> None:
        payload = tlv.load_policy()
        start = time.perf_counter()
        reports = [tlv.validate_target_live_validation_readiness_policy(payload) for _ in range(25)]
        elapsed = time.perf_counter() - start
        self.assertTrue(all(report["ok"] for report in reports), reports[-1]["failures"])
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
