#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_setup_mode_matrix_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test setup mode matrix validation.
Inputs: Workspace setup mode policy, setup mode matrix, docs and registry.
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

import setup_mode_matrix_runtime as smm


class SetupModeMatrixPerformanceTests(unittest.TestCase):
    def test_repeated_validation_stays_lightweight(self) -> None:
        policy = smm.load_policy(ROOT / "configs" / "setup-mode-matrix-policy.json")
        started = time.perf_counter()
        for _ in range(3):
            report = smm.validate_setup_mode_matrix_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
            self.assertTrue(report["ok"], report["failures"])
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 4.0)

    def test_setup_mode_docs_refs_stay_canonical_and_bounded(self) -> None:
        policy = smm.load_policy(ROOT / "configs" / "setup-mode-matrix-policy.json")
        refs = policy["policy"]["required_boundary_refs"]
        legacy_refs = {"README.md", "TODO.md", "noemaforge/TODO.md", "docs/SETUP_MODES.md"}
        started = time.perf_counter()
        for _ in range(2000):
            canonical = all(ref.startswith(("docs/", "noemaforge/docs/")) for ref in refs)
            onboarding = "docs/onboarding/SETUP_MODES.md" in refs
            legacy_free = legacy_refs.isdisjoint(refs)
            bounded = len(refs) <= 12
        elapsed = time.perf_counter() - started
        self.assertTrue(canonical)
        self.assertTrue(onboarding)
        self.assertTrue(legacy_free)
        self.assertTrue(bounded)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
