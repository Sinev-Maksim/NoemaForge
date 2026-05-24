#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_launcher_mount_normalization_performance.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test launcher mount path normalization.
Inputs: Synthetic legacy launcher paths.
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

import runtime_safety


class LauncherMountNormalizationPerformanceTests(unittest.TestCase):
    def test_launcher_path_normalization_stays_constant_time(self) -> None:
        start = time.perf_counter()
        for _ in range(20000):
            report = runtime_safety.normalize_launcher_paths(
                share_root="/mnt/brainos-share",
                vault_root="/mnt/brainos-share/brainos-lab/data/Vault",
                shortlist_file="/mnt/brainos-share/Vault/manifests/noemaforge-firstboot-shortlist.txt",
            )
        elapsed = time.perf_counter() - start

        self.assertEqual("/mnt/noemaforge-share", report["share_root"])
        self.assertLess(elapsed, 1.2)


if __name__ == "__main__":
    unittest.main()
