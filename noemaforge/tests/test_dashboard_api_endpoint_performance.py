#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_dashboard_api_endpoint_performance.py
Zone: gui/control-plane
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Bounded regression test for dashboard API endpoint payload generation.
Inputs: Offline dashboard API endpoint fixture.
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

import dashboard_api_endpoint_runtime as daer


class DashboardApiEndpointPerformanceTests(unittest.TestCase):
    def test_dashboard_api_generation_is_bounded(self) -> None:
        server = daer.build_offline_dashboard_server(package_root=ROOT)
        started = time.perf_counter()
        payload = {}
        for _ in range(750):
            payload = server.dashboard_api()
        elapsed = time.perf_counter() - started

        self.assertTrue(payload["ok"])
        self.assertLess(elapsed, 1.5, f"dashboard api generation took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
