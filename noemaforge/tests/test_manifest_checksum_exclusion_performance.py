#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_manifest_checksum_exclusion_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Performance-test bounded manifest/checksum exclusion scanning on synthetic paths.
Inputs: Synthetic path inventory.
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

import manifest_checksum_exclusion_runtime as mcer


class ManifestChecksumExclusionPerformanceTests(unittest.TestCase):
    def test_exclusion_path_scan_stays_bounded_for_large_inventory(self) -> None:
        excluded = {"trash", "__pycache__", ".pytest_cache", "node_modules"}
        paths = [f"noemaforge/configs/item-{index:05d}.json" for index in range(10000)]
        paths.extend(f"trash/run-{index:05d}/artifact.json" for index in range(250))
        paths.extend(f"noemaforge/src/__pycache__/mod-{index:05d}.pyc" for index in range(250))

        started = time.perf_counter()
        hits = sum(1 for path in paths if mcer._has_excluded_part(path, excluded))
        elapsed = time.perf_counter() - started

        self.assertEqual(500, hits)
        self.assertLess(elapsed, 0.25, f"manifest exclusion path scan took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
