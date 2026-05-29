#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_setup_default_path_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test Setup Default Path validation.
Inputs: Workspace Setup Default Path policy, setup script and registry.
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

import setup_default_path_runtime as sdp


class SetupDefaultPathPerformanceTests(unittest.TestCase):
    @unittest.skipIf(sys.platform == "win32", "wall-time threshold tuned for Linux/BigBro-BOS")
    def test_repeated_validation_stays_lightweight(self) -> None:
        policy = sdp.load_policy(ROOT / "configs" / "setup-default-path-policy.json")
        start = time.perf_counter()
        for _ in range(10):
            report = sdp.validate_setup_default_path_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - start

        self.assertTrue(report["ok"], report["failures"])
        self.assertLess(elapsed, 4.2)

    def test_setup_docs_refs_stay_canonical_and_bounded(self) -> None:
        policy = sdp.load_policy(ROOT / "configs" / "setup-default-path-policy.json")
        refs = policy["policy"]["required_boundary_refs"] + policy["policy"]["required_onboarding_refs"]
        legacy_refs = {"README.md", "TODO.md", "noemaforge/TODO.md", "docs/QUICKSTART_VM.md", "docs/SETUP_MODES.md"}

        start = time.perf_counter()
        for _ in range(2000):
            legacy_free = legacy_refs.isdisjoint(refs)
            direct_docs_are_canonical = all(
                not ref.startswith("docs/") or ref.startswith(("docs/onboarding/", "docs/operations/", "docs/backlog/", "docs/history/", "docs/reference/")) or ref in {"docs/README.md", "docs/TODO.md"}
                for ref in refs
            )
            bounded = len(refs) <= 16
        elapsed = time.perf_counter() - start

        self.assertTrue(legacy_free)
        self.assertTrue(direct_docs_are_canonical)
        self.assertTrue(bounded)
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
