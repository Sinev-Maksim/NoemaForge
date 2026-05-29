#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_multios_runtime_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Performance-test MultiOS runtime contract validation on a synthetic profile catalog.
Inputs: Workspace policy expanded with hundreds of optional runtime profiles.
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

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

import multios_runtime_contract as mrc
from noemaforge.runtime.registry import load_runtime_policy


class MultiOSRuntimePerformanceTests(unittest.TestCase):
    def test_synthetic_runtime_profile_catalog_validates_under_budget(self) -> None:
        payload = copy.deepcopy(load_runtime_policy(ROOT / "configs" / "noemaforge.runtime.yaml"))
        base_profiles = copy.deepcopy(payload["profiles"])
        payload["profiles"] = []
        for index in range(75):
            for profile in base_profiles:
                clone = copy.deepcopy(profile)
                clone["id"] = f"{profile['id']}-{index:03d}"
                payload["profiles"].append(clone)
        payload["profiles"].extend(base_profiles)

        started = time.perf_counter()
        report = mrc.validate_multios_runtime_policy(payload, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(304, report["metrics"]["profiles"])
        self.assertEqual(304, report["metrics"]["passing_profiles"])
        self.assertEqual(76, report["metrics"]["linux_profiles"])
        self.assertEqual(76, report["metrics"]["windows_profiles"])
        self.assertEqual(76, report["metrics"]["macos_profiles"])
        self.assertEqual(76, report["metrics"]["remote_profiles"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
