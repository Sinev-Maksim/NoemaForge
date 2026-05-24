#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_selftest_event_store_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test self-test event storage on synthetic reports.
Inputs: Synthetic report series only.
Outputs: unittest assertions only.
Side effects: Temporary SQLite files under unittest temp directories only.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import selftest_runtime as strt


def synthetic_report(run_id: str, cases: int = 220) -> dict:
    results = []
    for index in range(cases):
        results.append({
            "case_id": f"case_{index:03d}",
            "module": "synthetic",
            "tier": "performance",
            "status": "pass",
            "metrics": {"duration_sec": 0.01 + index * 0.0001, "max_rss_kib": 9000 + index, "disk_write_bytes": 8},
        })
    return {
        "apiVersion": "noemaforge/v1",
        "kind": "SelfTestReport",
        "version": "0.31.13.alpha-patched1",
        "run_id": run_id,
        "suite": "synthetic",
        "started_at": "2026-05-20T02:56:00Z",
        "finished_at": "2026-05-20T02:56:05Z",
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


class SelfTestEventStorePerformanceTests(unittest.TestCase):
    def test_synthetic_event_store_ingest_and_export_stays_lightweight(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            state = Path(raw) / "state"
            conn = strt.db_connect(state)
            start = time.perf_counter()
            try:
                for index in range(8):
                    events = strt.record_test_events_for_report(conn, synthetic_report(f"perf_{index}"))
            finally:
                conn.close()
            export = strt.export_test_events(state, limit=2000)
            elapsed = time.perf_counter() - start

        self.assertEqual(221, len(events))
        self.assertEqual(1768, export["event_count"])
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
