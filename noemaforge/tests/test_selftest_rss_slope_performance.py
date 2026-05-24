#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_selftest_rss_slope_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test self-test RSS slope analysis on synthetic repeated reports.
Inputs: Synthetic report series only.
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

import selftest_runtime as strt


def synthetic_repeat_report(cases: int = 260, repeats: int = 6) -> dict:
    results = []
    for index in range(cases):
        base = 8000 + index
        slope = 20 if index % 20 else 900
        sequence = [base + slope * repeat for repeat in range(repeats)]
        results.append({
            "case_id": f"case_{index:03d}",
            "module": "synthetic",
            "tier": "stress",
            "status": "pass",
            "metrics": {"duration_sec": 0.01, "max_rss_kib": sequence[-1]},
            "repeats": {"count": repeats, "max_rss_kib_sequence": sequence, "memory_leak_suspect": slope >= 900},
        })
    return {
        "apiVersion": "noemaforge/v1",
        "kind": "SelfTestReport",
        "version": "0.31.13.alpha-patched1",
        "run_id": "synthetic_rss",
        "suite": "stress",
        "summary": {"ok": True, "case_count": cases, "passed": cases, "failed": 0, "duration_total_sec": 1.0, "duration_max_sec": 0.01, "max_rss_kib": max(item["metrics"]["max_rss_kib"] for item in results), "disk_write_bytes_total": 0, "ecc_delta_total": 0},
        "results": results,
    }


class SelfTestRssSlopePerformanceTests(unittest.TestCase):
    def test_synthetic_rss_slope_analysis_stays_lightweight(self) -> None:
        report = synthetic_repeat_report()
        start = time.perf_counter()
        for _ in range(80):
            slope_report = strt.build_rss_slope_report(report, warn_slope_kib=512, fail_slope_kib=2048, min_repeats=3)
        elapsed = time.perf_counter() - start

        self.assertEqual(260, slope_report["summary"]["analyzed_cases"])
        self.assertEqual(13, slope_report["summary"]["failures"])
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
