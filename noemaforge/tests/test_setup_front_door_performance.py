#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_setup_front_door_performance.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test Setup Front Door validation.
Inputs: Workspace Setup Front Door policy, setup script and registry.
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

import setup_front_door_runtime as sfd


class SetupFrontDoorPerformanceTests(unittest.TestCase):
    def test_repeated_validation_stays_lightweight(self) -> None:
        policy = sfd.load_policy(ROOT / "configs" / "setup-front-door-policy.json")
        start = time.perf_counter()
        for _ in range(10):
            report = sfd.validate_setup_front_door_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - start

        self.assertTrue(report["ok"], report["failures"])
        self.assertLess(elapsed, 4.2)

    def test_front_door_docs_refs_stay_canonical_and_bounded(self) -> None:
        policy = sfd.load_policy(ROOT / "configs" / "setup-front-door-policy.json")
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
