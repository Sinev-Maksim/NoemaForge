#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_cli_install_wiring_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Bounded regression test for pipeline CLI install wiring validation.
Inputs: Pipeline CLI install wiring policy and local installer scripts.
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

import pipeline_cli_install_wiring_runtime as pciw


class PipelineCliInstallWiringPerformanceTests(unittest.TestCase):
    def test_installer_and_cli_analysis_stays_bounded(self) -> None:
        policy = pciw.load_policy()
        started = time.perf_counter()
        reports = [
            pciw.analyze_pipeline_cli_install_wiring(policy, project_root=PROJECT_ROOT, package_root=ROOT)
            for _ in range(60)
        ]
        elapsed = time.perf_counter() - started
        self.assertTrue(all(not item["failures"] for item in reports), reports[-1]["failures"])
        self.assertEqual(33, reports[-1]["summary"]["pipeline_command_count"])
        self.assertLess(elapsed, 1.0)

    def test_policy_validation_stays_bounded(self) -> None:
        policy = pciw.load_policy()
        started = time.perf_counter()
        reports = [
            pciw.validate_pipeline_cli_install_wiring_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
            for _ in range(20)
        ]
        elapsed = time.perf_counter() - started
        self.assertTrue(all(item["ok"] for item in reports), reports[-1]["failures"])
        self.assertLess(elapsed, 1.5)


if __name__ == "__main__":
    unittest.main()
