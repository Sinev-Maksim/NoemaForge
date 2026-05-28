#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_sense_layer_edge_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Performance-test Sense Layer Edge validation on a synthetic adapter catalog.
Inputs: Workspace policy expanded with hundreds of offline adapters.
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

import sense_layer_edge_runtime as sler


class SenseLayerEdgePerformanceTests(unittest.TestCase):
    def test_synthetic_adapter_catalog_validates_under_budget(self) -> None:
        payload = copy.deepcopy(sler.load_policy(ROOT / "configs" / "sense-layer-edge.json"))
        base_adapters = copy.deepcopy(payload["adapters"])
        payload["adapters"] = []
        for index in range(150):
            for adapter in base_adapters:
                clone = copy.deepcopy(adapter)
                clone["id"] = f"{adapter['id']}-{index:04d}"
                clone["source_id"] = f"{adapter['source_id']}-{index:04d}"
                payload["adapters"].append(clone)

        started = time.perf_counter()
        report = sler.validate_sense_layer_edge_policy(payload, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:5])
        self.assertEqual(450, report["metrics"]["adapters"])
        self.assertEqual(450, report["metrics"]["passing_adapters"])
        self.assertEqual(150, report["metrics"]["mqtt_adapters"])
        self.assertEqual(150, report["metrics"]["serial_adapters"])
        self.assertEqual(150, report["metrics"]["system_metrics_adapters"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
