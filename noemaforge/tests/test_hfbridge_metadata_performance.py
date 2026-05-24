#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_hfbridge_metadata_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test HFBridge validation on synthetic metadata-query catalogs.
Inputs: Workspace policy expanded with hundreds of HFBridgeMetadataQuery records.
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

import hfbridge_metadata_runtime as hmr


class HFBridgeMetadataPerformanceTests(unittest.TestCase):
    def test_synthetic_hfbridge_catalog_validates_under_budget(self) -> None:
        policy = hmr.load_policy(ROOT / "configs" / "hfbridge-metadata-policy.json")
        base_set = hmr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "hfbridge_metadata.example.json")
        synthetic_set = copy.deepcopy(base_set)
        base_queries = copy.deepcopy(base_set["queries"])
        synthetic_set["queries"] = []
        for index in range(300):
            query = copy.deepcopy(base_queries[index % len(base_queries)])
            query["id"] = f"{query['id']}-{index:03d}"
            query["trace_id"] = f"{query['trace_id']}:{index:03d}"
            query["target_ref"] = f"{query['target_ref']}-{index:03d}"
            synthetic_set["queries"].append(query)

        started = time.perf_counter()
        with patch.object(hmr, "load_example_set", return_value=synthetic_set):
            report = hmr.validate_hfbridge_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["queries"])
        self.assertEqual(300, report["metrics"]["passing_queries"])
        self.assertEqual(5, report["metrics"]["allowed_operations"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
