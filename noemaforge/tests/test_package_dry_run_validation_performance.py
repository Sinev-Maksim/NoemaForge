#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_package_dry_run_validation_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test package dry-run validation on synthetic scenario catalogs.
Inputs: Workspace policy expanded with hundreds of package dry-run scenarios.
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

import package_dry_run_validation_runtime as pdvr


class PackageDryRunValidationPerformanceTests(unittest.TestCase):
    def test_synthetic_package_dry_run_catalog_validates_under_budget(self) -> None:
        policy = pdvr.load_policy(ROOT / "configs" / "package-dry-run-validation-policy.json")
        base_set = pdvr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "package_dry_run_validation.example.json")
        base_scenario = base_set["scenarios"][0]
        synthetic_set = copy.deepcopy(base_set)
        synthetic_set["scenarios"] = []
        for index in range(300):
            scenario = copy.deepcopy(base_scenario)
            scenario["id"] = f"setup-vm-dry-run-selftest-{index:03d}"
            scenario["trace_id"] = f"trace:package-dry-run:setup-vm-selftest:{index:03d}"
            scenario["command"] = ["./setup.sh", "--mode", "vm", "--dry-run", "--selftest", "--install-root", f"/tmp/noemaforge-rootfs-{index:03d}"]
            synthetic_set["scenarios"].append(scenario)

        started = time.perf_counter()
        with patch.object(pdvr, "load_example_set", return_value=synthetic_set):
            report = pdvr.validate_package_dry_run_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["scenarios"])
        self.assertEqual(300, report["metrics"]["passing_scenarios"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
