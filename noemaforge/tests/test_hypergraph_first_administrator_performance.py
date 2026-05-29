#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_hypergraph_first_administrator_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test Hypergraph-First Administrator validation.
Inputs: Workspace Hypergraph-First Administrator policy and public docs.
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

import hypergraph_first_administrator_runtime as hfa


class HypergraphFirstAdministratorPerformanceTests(unittest.TestCase):
    def test_repeated_hypergraph_first_administrator_validation_stays_lightweight(self) -> None:
        policy = hfa.load_policy(ROOT / "configs" / "hypergraph-first-administrator-policy.json")
        start = time.perf_counter()
        for _ in range(8):
            report = hfa.validate_hypergraph_first_administrator_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - start

        self.assertTrue(report["ok"], report["failures"])
        self.assertLess(elapsed, 3.5)


if __name__ == "__main__":
    unittest.main()
