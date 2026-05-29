#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_stateful_admin_gui_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test the offline stateful Admin GUI install validator.
Inputs: Workspace stateful-admin-gui policy and local source files.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import stateful_admin_gui_runtime as sagr


@unittest.skipIf(sys.platform == "win32", "wall-time threshold tuned for Linux/BigBro-BOS")
class StatefulAdminGuiPerformanceTests(unittest.TestCase):
    def test_offline_stateful_admin_gui_validator_is_fast_enough_for_install_gate(self) -> None:
        result = sagr.benchmark_stateful_admin_gui(package_root=ROOT, iterations=60)

        self.assertTrue(result["ok"], result)
        self.assertEqual(0, result["failures"], result)
        self.assertLess(result["elapsed_seconds"], 5.0, result)
        self.assertGreater(result["iterations_per_second"], 5.0, result)


if __name__ == "__main__":
    unittest.main()
