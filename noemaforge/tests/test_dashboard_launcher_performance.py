#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_dashboard_launcher_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test dashboard launcher validation on synthetic scenario catalogs.
Inputs: Workspace policy expanded with hundreds of dashboard launcher scenarios.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import dashboard_launcher_runtime as dlr


class DashboardLauncherPerformanceTests(unittest.TestCase):
    def test_synthetic_dashboard_launcher_catalog_validates_under_budget(self) -> None:
        policy = dlr.load_policy(ROOT / "configs" / "dashboard-launcher-policy.json")
        base_set = dlr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "dashboard_launcher.example.json")
        base_scenario = base_set["scenarios"][0]
        synthetic_set = copy.deepcopy(base_set)
        synthetic_set["scenarios"] = []
        for index in range(300):
            scenario = copy.deepcopy(base_scenario)
            scenario["id"] = f"dashboard-path-state-{index:03d}"
            scenario["trace_id"] = f"trace:dashboard:launcher:path-state:{index:03d}"
            synthetic_set["scenarios"].append(scenario)

        started = time.perf_counter()
        with patch.object(dlr, "load_example_set", return_value=synthetic_set):
            report = dlr.validate_dashboard_launcher_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["scenarios"])
        self.assertEqual(300, report["metrics"]["passing_scenarios"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
