#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_edge_reference_targets_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Performance-test Edge Reference Targets validation on a synthetic reference catalog.
Inputs: Workspace policy expanded with hundreds of optional edge reference targets.
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

import edge_reference_targets_runtime as ertr


class EdgeReferenceTargetsPerformanceTests(unittest.TestCase):
    def test_synthetic_reference_catalog_validates_under_budget(self) -> None:
        payload = copy.deepcopy(ertr.load_policy(ROOT / "configs" / "edge-reference-targets.json"))
        base_targets = copy.deepcopy(payload["targets"])
        payload["policy"]["required_targets"] = [target["id"] for target in base_targets]
        payload["targets"] = []
        for index in range(125):
            for target in base_targets:
                clone = copy.deepcopy(target)
                clone["local_mvp_alternative_ref"] = target["local_mvp_alternative_ref"]
                payload["targets"].append(clone)

        started = time.perf_counter()
        report = ertr.validate_edge_reference_targets_policy(payload, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:5])
        self.assertEqual(500, report["metrics"]["targets"])
        self.assertEqual(500, report["metrics"]["passing_targets"])
        self.assertEqual(125, report["metrics"]["orchestration_targets"])
        self.assertEqual(125, report["metrics"]["stream_rule_engine_targets"])
        self.assertEqual(250, report["metrics"]["ota_reference_targets"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
