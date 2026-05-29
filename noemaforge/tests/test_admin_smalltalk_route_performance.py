#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_smalltalk_route_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test repeated static Admin smalltalk route validation.
Inputs: Workspace admin-smalltalk-route policy and Admin runtimes.
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
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import admin_smalltalk_route_runtime as asr


class AdminSmalltalkRoutePerformanceTests(unittest.TestCase):
    def test_repeated_static_validation_stays_under_budget(self) -> None:
        policy = asr.load_policy(ROOT / "configs" / "admin-smalltalk-route-policy.json")
        started = time.perf_counter()
        for _ in range(100):
            report = asr.validate_admin_smalltalk_route_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
            self.assertTrue(report["ok"], report["failures"])
            self.assertFalse(asr.build_admin_smalltalk_decision("thanks")["launches_pipeline"])
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
