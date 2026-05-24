#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_roleflow_orchestration_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test RoleFlow validation on synthetic orchestration catalogs.
Inputs: Workspace policy expanded with hundreds of RoleFlow records.
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

import roleflow_orchestration_runtime as rfor


class RoleFlowOrchestrationPerformanceTests(unittest.TestCase):
    def test_synthetic_roleflow_catalog_validates_under_budget(self) -> None:
        policy = rfor.load_policy(ROOT / "configs" / "roleflow-orchestration-policy.json")
        base_set = rfor.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "roleflow_orchestration.example.json")
        synthetic_set = copy.deepcopy(base_set)
        base_flow = copy.deepcopy(base_set["flows"][0])
        synthetic_set["flows"] = []
        for index in range(300):
            flow = copy.deepcopy(base_flow)
            flow["id"] = f"{flow['id']}-{index:03d}"
            flow["trace_id"] = f"{flow['trace_id']}:{index:03d}"
            synthetic_set["flows"].append(flow)

        started = time.perf_counter()
        with patch.object(rfor, "load_example_set", return_value=synthetic_set):
            report = rfor.validate_roleflow_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["flows"])
        self.assertEqual(300, report["metrics"]["passing_flows"])
        self.assertEqual(4, report["metrics"]["kernel_roles"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
