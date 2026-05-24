#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_job_progress_stream_performance.py
Zone: gui/control-plane
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test bounded SSE event planning for many jobs.
Inputs: Synthetic job records.
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

import job_progress_stream_runtime as jpsr


class JobProgressStreamPerformanceTests(unittest.TestCase):
    def test_sse_event_planning_stays_bounded_for_many_jobs(self) -> None:
        jobs = [
            {
                "job_id": f"job_{index:05d}",
                "kind": "synthetic",
                "status": "running" if index % 3 else "queued",
                "progress": {"step": index % 7, "total": 7},
            }
            for index in range(5000)
        ]

        started = time.perf_counter()
        events = jpsr.build_job_stream_events(jobs)
        text = jpsr.format_sse_events(events)
        elapsed = time.perf_counter() - started

        self.assertEqual(21, len(events))
        self.assertIn("event: jobs_snapshot", text)
        self.assertIn("event: job_progress", text)
        self.assertLess(elapsed, 0.35, f"job progress stream planning took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
