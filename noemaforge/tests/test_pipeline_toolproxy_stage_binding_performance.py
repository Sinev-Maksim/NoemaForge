#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_toolproxy_stage_binding_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Bound regression cost for pipeline ToolProxy stage-binding generation.
Inputs: Small deterministic pipeline/stage fixture.
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
sys.path.insert(0, str(ROOT / "src"))

import pipeline_runtime as pr


class PipelineToolProxyStageBindingPerformanceTests(unittest.TestCase):
    def test_binding_generation_stays_bounded_for_small_ci_fixture(self) -> None:
        stages = [
            "intake",
            "architecture_clarification",
            "development",
            "unit_testing",
            "integration_testing",
            "optimization",
            "review",
            "merge_plan",
        ]
        started = time.perf_counter()
        total_actions = 0
        for _ in range(400):
            for stage in stages:
                binding = pr.build_toolproxy_stage_binding("evolution", stage, "ask_before_write")
                total_actions += len(binding["allowed_actions"])
        elapsed = time.perf_counter() - started
        self.assertGreater(total_actions, 0)
        self.assertLess(elapsed, 2.0, f"stage binding generation took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
