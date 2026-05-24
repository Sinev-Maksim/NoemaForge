#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_grounded_administrator_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test Grounded Administrator validation.
Inputs: Workspace Grounded Administrator policy and public docs.
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

import grounded_administrator_runtime as gar


class GroundedAdministratorPerformanceTests(unittest.TestCase):
    def test_repeated_grounded_administrator_validation_stays_lightweight(self) -> None:
        policy = gar.load_policy(ROOT / "configs" / "grounded-administrator-policy.json")
        start = time.perf_counter()
        for _ in range(8):
            report = gar.validate_grounded_administrator_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - start

        self.assertTrue(report["ok"], report["failures"])
        self.assertLess(elapsed, 3.5)


if __name__ == "__main__":
    unittest.main()
