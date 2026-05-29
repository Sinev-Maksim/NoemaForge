#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_memory_budgeted_retrieval_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test Memory-Budgeted Retrieval validation.
Inputs: Workspace Memory-Budgeted Retrieval policy and public docs.
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

import memory_budgeted_retrieval_runtime as mbr


class MemoryBudgetedRetrievalPerformanceTests(unittest.TestCase):
    def test_repeated_memory_budgeted_retrieval_validation_stays_lightweight(self) -> None:
        policy = mbr.load_policy(ROOT / "configs" / "memory-budgeted-retrieval-policy.json")
        start = time.perf_counter()
        for _ in range(8):
            report = mbr.validate_memory_budgeted_retrieval_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - start

        self.assertTrue(report["ok"], report["failures"])
        self.assertLess(elapsed, 3.5)


if __name__ == "__main__":
    unittest.main()
