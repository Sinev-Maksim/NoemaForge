#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_alpha_backlog_fence_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test Alpha Backlog Fence validation on synthetic fence catalogs.
Inputs: Workspace policy expanded with hundreds of AlphaBacklogFence records.
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

import alpha_backlog_fence_runtime as abfr


class AlphaBacklogFencePerformanceTests(unittest.TestCase):
    def test_synthetic_alpha_backlog_fence_catalog_validates_under_budget(self) -> None:
        policy = abfr.load_policy(ROOT / "configs" / "alpha-backlog-fence.json")
        base_set = abfr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "alpha_backlog_fence.example.json")
        synthetic_set = copy.deepcopy(base_set)
        base_fence = copy.deepcopy(base_set["fences"][0])
        synthetic_set["fences"] = []
        for index in range(300):
            fence = copy.deepcopy(base_fence)
            fence["id"] = f"{fence['id']}-{index:03d}"
            fence["trace_id"] = f"{fence['trace_id']}:{index:03d}"
            synthetic_set["fences"].append(fence)

        started = time.perf_counter()
        with patch.object(abfr, "load_example_set", return_value=synthetic_set):
            report = abfr.validate_alpha_backlog_fence_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["fences"])
        self.assertEqual(300, report["metrics"]["passing_fences"])
        self.assertEqual(1, report["metrics"]["protected_refs"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
