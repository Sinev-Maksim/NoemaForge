#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_dragdrop_editor_performance.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test bounded drag/drop stage reorder planning.
Inputs: Synthetic pipeline stage lists.
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

import pipeline_dragdrop_editor_runtime as pde


class PipelineDragDropEditorPerformanceTests(unittest.TestCase):
    def test_reorder_planning_stays_bounded_for_many_edits(self) -> None:
        stages = [f"stage_{index:02d}" for index in range(24)]

        started = time.perf_counter()
        current = stages
        for index in range(5000):
            current = pde.move_stage(current, index % len(current), (index * 7) % len(current))
        elapsed = time.perf_counter() - started

        self.assertEqual(24, len(current))
        self.assertEqual(sorted(stages), sorted(current))
        self.assertLess(elapsed, 0.35, f"drag/drop reorder planning took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
