#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_smarthome_local_control_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test SmartHome validation on synthetic device/action catalogs.
Inputs: Workspace policy expanded with hundreds of SmartHome devices and actions.
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

import smarthome_local_control_runtime as shcr


class SmartHomeLocalControlPerformanceTests(unittest.TestCase):
    def test_synthetic_smarthome_catalog_validates_under_budget(self) -> None:
        policy = shcr.load_policy(ROOT / "configs" / "smarthome-local-control-policy.json")
        base_set = shcr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "smarthome_local_control.example.json")
        synthetic_set = copy.deepcopy(base_set)
        base_devices = copy.deepcopy(base_set["device_registry"]["devices"])
        base_actions = copy.deepcopy(base_set["actions"])
        synthetic_set["device_registry"]["devices"] = []
        synthetic_set["actions"] = []
        for index in range(400):
            device = copy.deepcopy(base_devices[index % len(base_devices)])
            device["id"] = f"{device['id']}-{index:03d}"
            synthetic_set["device_registry"]["devices"].append(device)
            action = copy.deepcopy(base_actions[index % len(base_actions)])
            action["id"] = f"{action['id']}-{index:03d}"
            action["trace_id"] = f"{action['trace_id']}:{index:03d}"
            action["device_id"] = device["id"]
            synthetic_set["actions"].append(action)

        started = time.perf_counter()
        with patch.object(shcr, "load_example_set", return_value=synthetic_set):
            report = shcr.validate_smarthome_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(400, report["metrics"]["actions"])
        self.assertEqual(400, report["metrics"]["passing_actions"])
        self.assertEqual(1, report["metrics"]["device_registries"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
