#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_onboarding_ladder_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test onboarding ladder validation.
Inputs: Workspace onboarding ladder policy, docs and registry.
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

import onboarding_ladder_runtime as olr


class OnboardingLadderPerformanceTests(unittest.TestCase):
    def test_repeated_validation_stays_lightweight(self) -> None:
        policy = olr.load_policy(ROOT / "configs" / "onboarding-ladder-policy.json")
        started = time.perf_counter()
        for _ in range(3):
            report = olr.validate_onboarding_ladder_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
            self.assertTrue(report["ok"], report["failures"])
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 4.0)

    def test_onboarding_ladder_docs_refs_stay_canonical_and_bounded(self) -> None:
        policy = olr.load_policy(ROOT / "configs" / "onboarding-ladder-policy.json")
        refs = policy["policy"]["required_boundary_refs"]
        order = policy["policy"]["required_order"]
        legacy_refs = {
            "README.md",
            "TODO.md",
            "noemaforge/TODO.md",
            "docs/QUICKSTART_VM.md",
            "docs/SETUP_MODES.md",
            "docs/PRODUCTION_INSTALL_TRIXIE.md",
            "docs/MVP_OPERATOR_GUIDE.md",
        }
        started = time.perf_counter()
        for _ in range(2000):
            canonical_refs = all(ref.startswith(("docs/", "noemaforge/docs/")) for ref in refs)
            canonical_order = all(ref.startswith("docs/") for ref in order)
            onboarding = "docs/onboarding/QUICKSTART_VM.md" in refs
            legacy_free = legacy_refs.isdisjoint(refs) and legacy_refs.isdisjoint(order)
            bounded = len(refs) <= 20 and len(order) == 5
        elapsed = time.perf_counter() - started
        self.assertTrue(canonical_refs)
        self.assertTrue(canonical_order)
        self.assertTrue(onboarding)
        self.assertTrue(legacy_free)
        self.assertTrue(bounded)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
