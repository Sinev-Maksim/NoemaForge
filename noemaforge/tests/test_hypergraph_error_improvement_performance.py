#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_hypergraph_error_improvement_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test Hypergraph Error Improvement validation.
Inputs: Workspace Hypergraph Error Improvement policy, SQL schema and registry.
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

import hypergraph_error_improvement_runtime as hei


class HypergraphErrorImprovementPerformanceTests(unittest.TestCase):
    def test_repeated_validation_stays_lightweight(self) -> None:
        policy = hei.load_policy(ROOT / "configs" / "hypergraph-error-improvement-policy.json")
        start = time.perf_counter()
        for _ in range(8):
            report = hei.validate_hypergraph_error_improvement_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - start

        self.assertTrue(report["ok"], report["failures"])
        self.assertLess(elapsed, 4.2)

    def test_boundary_ref_contract_stays_canonical_and_bounded(self) -> None:
        policy = hei.load_policy(ROOT / "configs" / "hypergraph-error-improvement-policy.json")
        refs = policy["policy"]["required_boundary_refs"]
        legacy_refs = {"README.md", "TODO.md", "noemaforge/TODO.md"}

        start = time.perf_counter()
        for _ in range(2000):
            canonical = all(ref.startswith(("docs/", "noemaforge/docs/")) for ref in refs)
            bounded = len(refs) <= 12
            legacy_free = legacy_refs.isdisjoint(refs)
        elapsed = time.perf_counter() - start

        self.assertTrue(canonical)
        self.assertTrue(bounded)
        self.assertTrue(legacy_free)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
