#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_clean_distribution_allowlist_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test clean distribution validation on synthetic allowlist plans.
Inputs: Workspace policy expanded with hundreds of CleanDistributionPlan records.
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

import clean_distribution_allowlist_runtime as cdar


class CleanDistributionAllowlistPerformanceTests(unittest.TestCase):
    def test_synthetic_distribution_catalog_validates_under_budget(self) -> None:
        policy = cdar.load_policy(ROOT / "configs" / "clean-distribution-allowlist.json")
        base_set = cdar.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "clean_distribution_allowlist.example.json")
        synthetic_set = copy.deepcopy(base_set)
        base_plan = copy.deepcopy(base_set["plans"][0])
        synthetic_set["plans"] = []
        for index in range(250):
            plan = copy.deepcopy(base_plan)
            plan["id"] = f"{base_plan['id']}-{index:03d}"
            plan["trace_id"] = f"{base_plan['trace_id']}:{index:03d}"
            synthetic_set["plans"].append(plan)

        started = time.perf_counter()
        with patch.object(cdar, "load_example_set", return_value=synthetic_set):
            report = cdar.validate_clean_distribution_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(250, report["metrics"]["plans"])
        self.assertEqual(250, report["metrics"]["passing_plans"])
        self.assertEqual(4, report["metrics"]["category_rules"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
