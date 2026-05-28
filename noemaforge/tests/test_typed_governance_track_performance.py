#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_typed_governance_track_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test Typed Governance Track validation on synthetic track catalogs.
Inputs: Workspace policy expanded with hundreds of TypedGovernanceTrack records.
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

import typed_governance_track_runtime as tgtr


class TypedGovernanceTrackPerformanceTests(unittest.TestCase):
    def test_synthetic_typed_governance_track_catalog_validates_under_budget(self) -> None:
        policy = tgtr.load_policy(ROOT / "configs" / "typed-governance-track.json")
        base_set = tgtr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "typed_governance_track.example.json")
        synthetic_set = copy.deepcopy(base_set)
        base_track = copy.deepcopy(base_set["tracks"][0])
        synthetic_set["tracks"] = []
        for index in range(300):
            track = copy.deepcopy(base_track)
            track["id"] = f"{track['id']}-{index:03d}"
            track["trace_id"] = f"{track['trace_id']}:{index:03d}"
            synthetic_set["tracks"].append(track)

        started = time.perf_counter()
        with patch.object(tgtr, "load_example_set", return_value=synthetic_set):
            report = tgtr.validate_typed_governance_track_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["tracks"])
        self.assertEqual(300, report["metrics"]["passing_tracks"])
        self.assertEqual(8, report["metrics"]["contracts"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
