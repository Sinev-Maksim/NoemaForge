#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_artifact_registry_table_performance.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Bounded regression test for artifact registry table validation.
Inputs: Artifact registry table policy and example table.
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

import artifact_registry_table_runtime as art


class ArtifactRegistryTablePerformanceTests(unittest.TestCase):
    def test_table_summary_stays_bounded(self) -> None:
        records = art.load_example()["records"] * 200
        started = time.perf_counter()
        summaries = [art.summarize_artifact_registry_records(records) for _ in range(100)]
        elapsed = time.perf_counter() - started
        self.assertEqual(600, summaries[-1]["record_count"])
        self.assertEqual(200, summaries[-1]["graph_patch_records"])
        self.assertLess(elapsed, 0.25)

    def test_policy_validation_stays_bounded(self) -> None:
        policy = art.load_policy()
        started = time.perf_counter()
        reports = [
            art.validate_artifact_registry_table_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
            for _ in range(20)
        ]
        elapsed = time.perf_counter() - started
        self.assertTrue(all(item["ok"] for item in reports), reports[-1]["failures"])
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
