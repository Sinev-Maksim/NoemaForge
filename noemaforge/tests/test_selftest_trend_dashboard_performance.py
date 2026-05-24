#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_selftest_trend_dashboard_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test self-test trend dashboard generation on synthetic reports.
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


def synthetic_report(index: int, cases: int = 8) -> dict:
    failed = 1 if index % 17 == 0 else 0
    results = []
    for case in range(cases):
        status = "fail" if failed and case == cases - 1 else "pass"
        results.append({
            "case_id": f"case_{case:02d}",
            "module": "synthetic",
            "tier": "performance",
            "status": status,
            "metrics": {
                "duration_sec": 0.05 + (index * 0.001) + (case * 0.002),
                "max_rss_kib": 10000 + index + case,
                "disk_write_bytes": 32 + case,
            },
        })
    return {
        "apiVersion": "noemaforge/v1",
        "kind": "SelfTestReport",
        "version": "0.31.13.alpha-patched1",
        "run_id": f"selftest_20260520T{index:06d}Z",
        "suite": "synthetic",
        "started_at": f"2026-05-20T00:{index % 60:02d}:00Z",
        "finished_at": f"2026-05-20T00:{index % 60:02d}:01Z",
        "summary": {
            "ok": failed == 0,
            "case_count": cases,
            "passed": cases - failed,
            "failed": failed,
            "duration_total_sec": sum(item["metrics"]["duration_sec"] for item in results),
            "duration_max_sec": max(item["metrics"]["duration_sec"] for item in results),
            "max_rss_kib": max(item["metrics"]["max_rss_kib"] for item in results),
            "disk_write_bytes_total": sum(item["metrics"]["disk_write_bytes"] for item in results),
            "ecc_delta_total": 0,
        },
        "results": results,
    }


class SelfTestTrendDashboardPerformanceTests(unittest.TestCase):
    def test_synthetic_trend_dashboard_generation_stays_lightweight(self) -> None:
        reports = [synthetic_report(index) for index in range(160)]
        start = time.perf_counter()
        dashboard = strt.build_trend_dashboard(reports)
        html = strt.render_trend_dashboard_html(dashboard)
        elapsed = time.perf_counter() - start

        self.assertEqual(160, dashboard["run_count"])
        self.assertEqual(8, dashboard["case_count"])
        self.assertIn("self-test trend", html)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
