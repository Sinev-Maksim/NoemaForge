#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_concept_frame_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Performance-test Concept_Frame validation on a synthetic frame catalog.
Inputs: Workspace policy expanded with hundreds of Concept Frames.
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

import concept_frame_runtime as cfr


class ConceptFramePerformanceTests(unittest.TestCase):
    def test_synthetic_concept_frame_catalog_validates_under_budget(self) -> None:
        policy = cfr.load_policy(ROOT / "configs" / "concept-frame-policy.json")
        base_set = cfr.load_frame_set(PROJECT_ROOT / "prelaunch" / "governance" / "concept_frame.admin_architect.example.json")
        synthetic_set = copy.deepcopy(base_set)
        synthetic_set["frames"] = []
        for index in range(150):
            for frame in base_set["frames"]:
                clone = copy.deepcopy(frame)
                clone["id"] = f"{frame['id']}-{index:03d}"
                clone["trace_id"] = f"{frame['trace_id']}:{index:03d}"
                synthetic_set["frames"].append(clone)

        started = time.perf_counter()
        with patch.object(cfr, "load_frame_set", return_value=synthetic_set):
            report = cfr.validate_concept_frame_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["frames"])
        self.assertEqual(300, report["metrics"]["passing_frames"])
        self.assertEqual(150, report["metrics"]["admin_frames"])
        self.assertEqual(150, report["metrics"]["architect_frames"])
        self.assertEqual(150, report["metrics"]["dangerous_frames"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
