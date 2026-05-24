#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_public_showcase_guided_scenario_performance.py
Zone: gui/control-plane
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test public showcase guided scenario validation on bounded fixtures.
Inputs: Public showcase policy expanded with repeated safe refs and step ids.
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

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import public_showcase_guided_scenario_runtime as psg


class PublicShowcaseGuidedScenarioPerformanceTests(unittest.TestCase):
    def test_validation_stays_bounded_with_repeated_refs(self) -> None:
        policy = psg.load_policy(ROOT / "configs" / "public-showcase-guided-scenario-policy.json")
        expanded = copy.deepcopy(policy)
        expanded["refs"] = list(policy["refs"]) * 20
        start = time.perf_counter()
        report = psg.validate_public_showcase_guided_scenario_policy(expanded, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - start
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(len(expanded["refs"]), report["metrics"]["refs"])
        self.assertLess(elapsed, 2.5)


if __name__ == "__main__":
    unittest.main()
