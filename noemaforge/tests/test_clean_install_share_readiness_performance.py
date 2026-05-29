#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_clean_install_share_readiness_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Keep clean install share readiness checks bounded for local CI.
Inputs: Clean install share readiness policy and runtime validator.
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

import clean_install_share_readiness_runtime as cis


class CleanInstallShareReadinessPerformanceTests(unittest.TestCase):
    def test_readiness_validation_stays_bounded(self) -> None:
        payload = cis.load_policy()
        start = time.perf_counter()
        reports = [cis.validate_clean_install_share_readiness_policy(payload) for _ in range(25)]
        elapsed = time.perf_counter() - start
        self.assertTrue(all(report["ok"] for report in reports), reports[-1]["failures"])
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
