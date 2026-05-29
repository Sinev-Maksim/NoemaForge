#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_slop_critic_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test Slop Critic validation on synthetic cases.
Inputs: Workspace policy expanded with hundreds of SlopCriticCase records.
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

import slop_critic_runtime as scr


class SlopCriticPerformanceTests(unittest.TestCase):
    def test_synthetic_slop_critic_catalog_validates_under_budget(self) -> None:
        policy = scr.load_policy(ROOT / "configs" / "slop-critic-policy.json")
        base_set = scr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "slop_critic.example.json")
        synthetic_set = copy.deepcopy(base_set)
        base_cases = copy.deepcopy(base_set["cases"])
        base_scoring = copy.deepcopy(base_set["scoring_cases"][0])
        synthetic_set["cases"] = []
        synthetic_set["scoring_cases"] = []
        for index in range(300):
            case = copy.deepcopy(base_cases[index % len(base_cases)])
            case["id"] = f"{case['id']}-{index:03d}"
            case["trace_id"] = f"{case['trace_id']}:{index:03d}"
            synthetic_set["cases"].append(case)
            if index < 100:
                scoring_case = copy.deepcopy(base_scoring)
                scoring_case["id"] = f"{scoring_case['id']}-{index:03d}"
                synthetic_set["scoring_cases"].append(scoring_case)

        started = time.perf_counter()
        with patch.object(scr, "load_example_set", return_value=synthetic_set):
            report = scr.validate_slop_critic_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["cases"])
        self.assertEqual(300, report["metrics"]["passing_cases"])
        self.assertEqual(100, report["metrics"]["scoring_cases"])
        self.assertEqual(100, report["metrics"]["passing_scoring_cases"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
