#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_premerge_release_guard_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test pre-merge release guard on synthetic self-test reports.
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

import premerge_release_guard_runtime as prgr
import selftest_runtime as strt


def synthetic_report(run_id: str, cases: int = 180) -> dict:
    results = []
    for index in range(cases):
        case_id = "cli_status_json" if index == 0 else "pipeline_validate" if index == 1 else f"case_{index:03d}"
        results.append({
            "case_id": case_id,
            "module": "synthetic",
            "tier": "performance",
            "status": "pass",
            "metrics": {"duration_sec": 0.01 + index * 0.0001, "max_rss_kib": 9000 + index, "disk_write_bytes": 8},
        })
    return {
        "apiVersion": "noemaforge/v1",
        "kind": "SelfTestReport",
        "version": "0.32.1",
        "run_id": run_id,
        "suite": "synthetic",
        "summary": {
            "ok": True,
            "case_count": cases,
            "passed": cases,
            "failed": 0,
            "duration_total_sec": sum(item["metrics"]["duration_sec"] for item in results),
            "duration_max_sec": max(item["metrics"]["duration_sec"] for item in results),
            "max_rss_kib": max(item["metrics"]["max_rss_kib"] for item in results),
            "disk_write_bytes_total": sum(item["metrics"]["disk_write_bytes"] for item in results),
            "ecc_delta_total": 0,
        },
        "results": results,
    }


class PremergeReleaseGuardPerformanceTests(unittest.TestCase):
    def test_synthetic_premerge_guard_stays_lightweight(self) -> None:
        telemetry = strt.load_policy(ROOT)
        guard_policy = prgr.load_policy(ROOT / "configs" / "premerge-release-guard-policy.json")
        baseline = synthetic_report("baseline")
        current = synthetic_report("current")
        start = time.perf_counter()
        for _ in range(50):
            decision = strt.build_premerge_release_guard(baseline, current, telemetry, guard_policy)
        elapsed = time.perf_counter() - start
        self.assertTrue(decision["ok"], decision)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
