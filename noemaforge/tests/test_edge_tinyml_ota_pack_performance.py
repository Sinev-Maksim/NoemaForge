#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_edge_tinyml_ota_pack_performance.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test the offline Edge/TinyML/OTA aggregate pack validator.
Inputs: Workspace edge-tinyml-ota-pack policy and component policies.
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

import edge_tinyml_ota_pack_runtime as etop


class EdgeTinyMLOTAPackPerformanceTests(unittest.TestCase):
    def test_offline_edge_tinyml_ota_pack_validator_is_fast_enough_for_idle_gate(self) -> None:
        result = etop.benchmark_edge_tinyml_ota_pack(package_root=ROOT, iterations=20)

        self.assertTrue(result["ok"], result)
        self.assertEqual(0, result["failures"], result)
        self.assertLess(result["elapsed_seconds"], 8.0, result)
        self.assertGreater(result["iterations_per_second"], 2.0, result)


if __name__ == "__main__":
    unittest.main()
