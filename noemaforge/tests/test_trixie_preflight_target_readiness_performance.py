#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_trixie_preflight_target_readiness_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Keep Trixie preflight target readiness checks bounded for local CI.
Inputs: Trixie preflight target readiness policy and runtime validator.
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

import trixie_preflight_target_readiness_runtime as tptr


class TrixiePreflightTargetReadinessPerformanceTests(unittest.TestCase):
    def test_readiness_validation_stays_bounded(self) -> None:
        payload = tptr.load_policy()
        start = time.perf_counter()
        reports = [tptr.validate_trixie_preflight_target_readiness_policy(payload) for _ in range(25)]
        elapsed = time.perf_counter() - start
        self.assertTrue(all(report["ok"] for report in reports), reports[-1]["failures"])
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
