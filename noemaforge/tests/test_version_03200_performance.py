#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_version_03200_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-21
Purpose: Keep active 0.32.1 version-surface checks lightweight.
Inputs: Workspace version, release, setup, config and runtime files.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import time
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = PACKAGE_ROOT.parent
EXPECTED_VERSION = "0.32.1"


class Version03200PerformanceTests(unittest.TestCase):
    def test_active_version_surface_scan_stays_fast(self) -> None:
        started = time.perf_counter()
        files_checked = 0
        token_hits = 0

        text_paths = [
            PROJECT_ROOT / "VERSION",
            PACKAGE_ROOT / "VERSION",
            PROJECT_ROOT / "setup.sh",
            PROJECT_ROOT / "release.json",
            PROJECT_ROOT / "MANIFEST.json",
            PACKAGE_ROOT / "bin" / "noemaforge",
            PACKAGE_ROOT / "tools" / "prep" / "noemaforge-first-run-audit.sh",
        ]
        text_paths.extend((PACKAGE_ROOT / "src").glob("*_runtime.py"))
        text_paths.extend((PACKAGE_ROOT / "configs").glob("*.json"))

        for path in sorted(set(text_paths)):
            if not path.exists() or path.name == "unified-registry.json":
                continue
            files_checked += 1
            text = path.read_text(encoding="utf-8")
            token_hits += text.count(EXPECTED_VERSION)
            if path.suffix == ".json":
                json.loads(text)

        elapsed = time.perf_counter() - started
        self.assertGreaterEqual(files_checked, 40)
        self.assertGreaterEqual(token_hits, 20)
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
