#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_machine_local_defaults_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test repeated machine-local default validation.
Inputs: Workspace machine-local-defaults policy and static files.
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

import machine_local_defaults_runtime as mldr


class MachineLocalDefaultsPerformanceTests(unittest.TestCase):
    def test_repeated_static_validation_stays_under_budget(self) -> None:
        policy = mldr.load_policy(ROOT / "configs" / "machine-local-defaults-policy.json")
        started = time.perf_counter()
        for _ in range(100):
            report = mldr.validate_machine_local_defaults_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
            self.assertTrue(report["ok"], report["failures"])
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
