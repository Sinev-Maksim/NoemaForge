#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_model_profile_selection_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test model profile manifest validation.
Inputs: Model profile manifest catalog.
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

import model_profile_selection_runtime as mps
import model_profiles


class ModelProfileSelectionPerformanceTests(unittest.TestCase):
    def test_repeated_manifest_builds_stay_bounded(self) -> None:
        profiles = model_profiles.load_profiles(ROOT)
        start = time.perf_counter()
        for _ in range(250):
            for name in mps.REQUIRED_PROFILES:
                manifest = model_profiles.build_profile_manifest(profiles, name)
                self.assertEqual(1, manifest["runtime"]["max_active_llms"])
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 0.5)

    def test_model_profile_docs_refs_stay_canonical_and_bounded(self) -> None:
        policy = mps.load_policy(ROOT / "configs" / "model-profile-selection-policy.json")
        refs = policy["policy"]["required_boundary_refs"]
        legacy_refs = {"README.md", "TODO.md", "noemaforge/TODO.md"}

        start = time.perf_counter()
        for _ in range(2000):
            canonical = all(ref.startswith(("docs/", "noemaforge/docs/")) for ref in refs)
            legacy_free = legacy_refs.isdisjoint(refs)
            bounded = len(refs) <= 12
        elapsed = time.perf_counter() - start

        self.assertTrue(canonical)
        self.assertTrue(legacy_free)
        self.assertTrue(bounded)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
