#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_honesty_protocol_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Performance-test Honesty Protocol validation on synthetic cases.
Inputs: Workspace policy expanded with hundreds of HonestyCase records.
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

import honesty_protocol_runtime as hpr


class HonestyProtocolPerformanceTests(unittest.TestCase):
    def test_synthetic_honesty_protocol_catalog_validates_under_budget(self) -> None:
        policy = hpr.load_policy(ROOT / "configs" / "honesty-protocol-policy.json")
        base_set = hpr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "honesty_protocol.example.json")
        synthetic_set = copy.deepcopy(base_set)
        base_cases = copy.deepcopy(base_set["cases"])
        base_classification = copy.deepcopy(base_set["classification_cases"][0])
        synthetic_set["cases"] = []
        synthetic_set["classification_cases"] = []
        for index in range(300):
            case = copy.deepcopy(base_cases[index % len(base_cases)])
            case["id"] = f"{case['id']}-{index:03d}"
            case["trace_id"] = f"{case['trace_id']}:{index:03d}"
            synthetic_set["cases"].append(case)
            if index < 100:
                classification_case = copy.deepcopy(base_classification)
                classification_case["id"] = f"{classification_case['id']}-{index:03d}"
                classification_case["input"]["trace_id"] = f"{classification_case['input']['trace_id']}:{index:03d}"
                synthetic_set["classification_cases"].append(classification_case)

        started = time.perf_counter()
        with patch.object(hpr, "load_example_set", return_value=synthetic_set):
            report = hpr.validate_honesty_protocol_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["cases"])
        self.assertEqual(300, report["metrics"]["passing_cases"])
        self.assertEqual(100, report["metrics"]["classification_cases"])
        self.assertEqual(100, report["metrics"]["passing_classification_cases"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
