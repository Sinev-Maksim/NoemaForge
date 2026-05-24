#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_llama_server_launcher_gate_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test repeated static llama-server launcher gate validation.
Inputs: Workspace llama-server-launcher-gate policy and prep scripts.
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

import llama_server_launcher_gate_runtime as lsg


class LlamaServerLauncherGatePerformanceTests(unittest.TestCase):
    def test_repeated_static_validation_stays_under_budget(self) -> None:
        policy = lsg.load_policy(ROOT / "configs" / "llama-server-launcher-gate-policy.json")
        started = time.perf_counter()
        for _ in range(100):
            report = lsg.validate_llama_server_launcher_gate_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
            self.assertTrue(report["ok"], report["failures"])
            self.assertFalse(lsg.classify_ldd_output("libfoo.so => not found", rc=0)["ok"])
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
