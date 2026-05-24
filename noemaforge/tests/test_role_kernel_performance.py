#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_role_kernel_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test Role Kernel validation on synthetic kernel catalogs.
Inputs: Workspace policy expanded with hundreds of RoleKernel records.
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

import role_kernel_runtime as rkr


class RoleKernelPerformanceTests(unittest.TestCase):
    def test_synthetic_role_kernel_catalog_validates_under_budget(self) -> None:
        policy = rkr.load_policy(ROOT / "configs" / "role-kernel-policy.json")
        base_set = rkr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "role_kernel.example.json")
        synthetic_set = copy.deepcopy(base_set)
        base_kernel = copy.deepcopy(base_set["kernels"][0])
        synthetic_set["kernels"] = []
        for index in range(300):
            kernel = copy.deepcopy(base_kernel)
            kernel["id"] = f"{kernel['id']}-{index:03d}"
            kernel["trace_id"] = f"{kernel['trace_id']}:{index:03d}"
            synthetic_set["kernels"].append(kernel)

        started = time.perf_counter()
        with patch.object(rkr, "load_example_set", return_value=synthetic_set):
            report = rkr.validate_role_kernel_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["kernels"])
        self.assertEqual(300, report["metrics"]["passing_kernels"])
        self.assertEqual(4, report["metrics"]["default_roles"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
