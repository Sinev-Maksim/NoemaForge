#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_backlog_status_legend_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test bounded backlog status legend scanning on synthetic Markdown.
Inputs: Synthetic Markdown documents.
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

import backlog_status_legend_runtime as bslr


class BacklogStatusLegendPerformanceTests(unittest.TestCase):
    def test_status_legend_scan_stays_bounded_for_large_docs(self) -> None:
        policy = bslr.load_policy(ROOT / "configs" / "backlog-status-legend-policy.json")
        section = """Status legend:
- `planned`: open/not started.
- `in progress`: partially covered.
- `done`: complete.
- `explicit non-goal`: outside the ASAP window.

"""
        text = section * 2500

        started = time.perf_counter()
        violations = bslr.find_status_legend_violations(
            text,
            source="synthetic-large.md",
            forbidden_markers=policy["policy"]["forbidden_legend_markers"],
            window_lines=policy["policy"]["legend_window_lines"],
        )
        elapsed = time.perf_counter() - started

        self.assertEqual([], violations)
        self.assertLess(elapsed, 0.35, f"status legend scan took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
