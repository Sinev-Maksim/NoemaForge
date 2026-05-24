#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_role_corpus_binding_performance.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test Role Corpus Binding validation.
Inputs: Workspace Role Corpus Binding policy and role-eval catalog.
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

import role_corpus_binding_runtime as rcb


class RoleCorpusBindingPerformanceTests(unittest.TestCase):
    def test_repeated_role_corpus_binding_validation_stays_lightweight(self) -> None:
        policy = rcb.load_policy(ROOT / "configs" / "role-corpus-binding-policy.json")
        start = time.perf_counter()
        for _ in range(8):
            report = rcb.validate_role_corpus_binding_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - start

        self.assertTrue(report["ok"], report["failures"])
        self.assertLess(elapsed, 3.8)


if __name__ == "__main__":
    unittest.main()
