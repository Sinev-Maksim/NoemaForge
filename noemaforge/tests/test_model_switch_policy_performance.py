#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_model_switch_policy_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Bounded regression test for model switch policy validation.
Inputs: Model switch policy and example inventory.
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

import model_switch_policy_runtime as msp


class ModelSwitchPolicyPerformanceTests(unittest.TestCase):
    def test_model_switch_resolution_stays_bounded(self) -> None:
        policy = msp.load_policy()
        inventory = msp.load_example()["model_inventory"]
        started = time.perf_counter()
        decisions = [
            msp.resolve_model_switch(policy, "administrator", inventory, remote_approved=False)
            for _ in range(200)
        ]
        elapsed = time.perf_counter() - started
        self.assertTrue(all(item["decision"] == "selected" for item in decisions))
        self.assertLess(elapsed, 0.25)

    def test_policy_validation_stays_bounded(self) -> None:
        policy = msp.load_policy()
        started = time.perf_counter()
        reports = [
            msp.validate_model_switch_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
            for _ in range(20)
        ]
        elapsed = time.perf_counter() - started
        self.assertTrue(all(item["ok"] for item in reports), reports[-1]["failures"])
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
