#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_editor_pack_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test the offline Pipeline Editor pack validator.
Inputs: Workspace pipeline-editor-pack policy and local source files.
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

import pipeline_editor_pack_runtime as pepr


class PipelineEditorPackPerformanceTests(unittest.TestCase):
    def test_offline_pipeline_editor_pack_validator_is_fast_enough_for_idle_gate(self) -> None:
        result = pepr.benchmark_pipeline_editor_pack(package_root=ROOT, iterations=120)

        self.assertTrue(result["ok"], result)
        self.assertEqual(0, result["failures"], result)
        self.assertLess(result["elapsed_seconds"], 6.0, result)
        self.assertGreater(result["iterations_per_second"], 20.0, result)


if __name__ == "__main__":
    unittest.main()
