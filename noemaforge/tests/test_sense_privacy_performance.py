#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_sense_privacy_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Performance-test Sense Privacy validation on synthetic Sense_State records.
Inputs: Workspace policy expanded with hundreds of sanitized Sense_State records.
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

import sense_privacy_runtime as spr


class SensePrivacyPerformanceTests(unittest.TestCase):
    def test_synthetic_sense_privacy_catalog_validates_under_budget(self) -> None:
        policy = spr.load_policy(ROOT / "configs" / "sense-privacy-policy.json")
        base_set = spr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "sense_privacy.example.json")
        synthetic_set = copy.deepcopy(base_set)
        base_state = copy.deepcopy(base_set["states"][0])
        base_case = copy.deepcopy(base_set["filter_cases"][0])
        synthetic_set["states"] = []
        synthetic_set["filter_cases"] = []
        for index in range(300):
            state = copy.deepcopy(base_state)
            state["id"] = f"{base_state['id']}-{index:03d}"
            state["trace_id"] = f"{base_state['trace_id']}:{index:03d}"
            synthetic_set["states"].append(state)
            if index < 100:
                case = copy.deepcopy(base_case)
                case["id"] = f"{base_case['id']}-{index:03d}"
                synthetic_set["filter_cases"].append(case)

        started = time.perf_counter()
        with patch.object(spr, "load_example_set", return_value=synthetic_set):
            report = spr.validate_sense_privacy_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["states"])
        self.assertEqual(300, report["metrics"]["passing_states"])
        self.assertEqual(100, report["metrics"]["filter_cases"])
        self.assertEqual(100, report["metrics"]["passing_filter_cases"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
