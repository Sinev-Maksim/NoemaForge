#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_rfc_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test Pipeline RFC validation on synthetic RFC catalogs.
Inputs: Workspace policy expanded with hundreds of PipelineRFC records.
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

import pipeline_rfc_runtime as prr


class PipelineRFCPerformanceTests(unittest.TestCase):
    def test_synthetic_pipeline_rfc_catalog_validates_under_budget(self) -> None:
        policy = prr.load_policy(ROOT / "configs" / "pipeline-rfc-policy.json")
        base_set = prr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "pipeline_rfc.example.json")
        synthetic_set = copy.deepcopy(base_set)
        base_rfcs = copy.deepcopy(base_set["rfcs"])
        base_scoring = copy.deepcopy(base_set["scoring_cases"][0])
        synthetic_set["rfcs"] = []
        synthetic_set["scoring_cases"] = []
        for index in range(300):
            rfc = copy.deepcopy(base_rfcs[index % len(base_rfcs)])
            rfc["id"] = f"{rfc['id']}-{index:03d}"
            rfc["trace_id"] = f"{rfc['trace_id']}:{index:03d}"
            synthetic_set["rfcs"].append(rfc)
            if index < 100:
                scoring_case = copy.deepcopy(base_scoring)
                scoring_case["id"] = f"{scoring_case['id']}-{index:03d}"
                synthetic_set["scoring_cases"].append(scoring_case)

        started = time.perf_counter()
        with patch.object(prr, "load_example_set", return_value=synthetic_set):
            report = prr.validate_pipeline_rfc_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["rfcs"])
        self.assertEqual(300, report["metrics"]["passing_rfcs"])
        self.assertEqual(100, report["metrics"]["scoring_cases"])
        self.assertEqual(100, report["metrics"]["passing_scoring_cases"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
