#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_firstboot_launcher_idempotency_performance.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test synthetic firstboot launcher lease cycles.
Inputs: Temporary synthetic launcher lease directories.
Outputs: unittest assertions only.
Side effects: Temporary-directory file writes only.
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

import firstboot_status


class FirstbootLauncherIdempotencyPerformanceTests(unittest.TestCase):
    def test_many_launcher_lease_cycles_stay_under_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            started = time.perf_counter()
            for index in range(250):
                run_dir = root / f"run-{index:03d}"
                run_dir.mkdir()
                status = run_dir / "firstboot-status.json"
                events = run_dir / "firstboot-events.jsonl"
                lease = firstboot_status.acquire_run_lease(str(status), str(events))
                self.assertTrue(lease["ok"], lease)
                released = firstboot_status.release_run_lease(str(status))
                self.assertTrue(released["ok"], released)
            elapsed = time.perf_counter() - started

            self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
