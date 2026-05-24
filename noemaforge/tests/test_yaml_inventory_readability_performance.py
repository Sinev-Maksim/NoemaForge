#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_yaml_inventory_readability_performance.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Performance-test bounded YAML readability linting on synthetic YAML.
Inputs: Synthetic YAML documents.
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

import yaml_inventory_readability_runtime as yirr


class YamlInventoryReadabilityPerformanceTests(unittest.TestCase):
    def test_yaml_lite_lint_stays_bounded_for_large_fixture(self) -> None:
        rows = ["items:"]
        for index in range(6000):
            rows.append(f"  - id: item-{index}")
            rows.append(f"    values: [{index}, ok, stable]")
        text = "\n".join(rows) + "\n"

        started = time.perf_counter()
        failures = yirr.lint_yaml_text(text, source="synthetic-large.yaml")
        elapsed = time.perf_counter() - started

        self.assertEqual([], failures)
        self.assertLess(elapsed, 0.45, f"YAML readability lint took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
