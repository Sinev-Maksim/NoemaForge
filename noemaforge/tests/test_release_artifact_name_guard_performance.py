#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_release_artifact_name_guard_performance.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Performance-test bounded release artifact filename matching.
Inputs: Synthetic filename inventory.
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
sys.path.insert(0, str(ROOT / "src"))

import release_artifact_name_guard_runtime as rang


class ReleaseArtifactNameGuardPerformanceTests(unittest.TestCase):
    def test_filename_pattern_matching_stays_bounded_for_large_inventory(self) -> None:
        patterns = ["CHANGELOG_*", "RELEASE_NOTES_*", "VERIFICATION_REPORT_*", "deep-research-report*", "source-report*"]
        names = [f"artifact-{index:05d}.json" for index in range(25000)]
        names.extend(
            [
                "CHANGELOG_shadow.md",
                "RELEASE_NOTES_shadow.md",
                "VERIFICATION_REPORT_shadow.md",
                "deep-research-report-9.md",
                "source-report-1.md",
            ]
        )

        started = time.perf_counter()
        hits = [name for name in names if rang._filename_matches_any(name, patterns)]
        elapsed = time.perf_counter() - started

        self.assertEqual(5, len(hits))
        self.assertLess(elapsed, 0.5, f"release artifact filename scan took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
