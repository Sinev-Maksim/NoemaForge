#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_firstboot_progress_performance.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test firstboot progress rendering on large event logs.
Inputs: Synthetic firstboot event streams.
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

import firstboot_progress_runtime as fbp


class FirstbootProgressPerformanceTests(unittest.TestCase):
    def test_large_event_log_progress_render_stays_bounded(self) -> None:
        events = []
        for idx in range(250):
            for phase in fbp.REQUIRED_PHASES:
                events.append({"ts": f"2026-05-20T07:{idx % 60:02d}:00Z", "step": phase, "state": "complete", "message": phase})
        start = time.perf_counter()
        view = fbp.build_progress_view(events, status={"state": "applied_no_reboot"}, staffing={"missing_mandatory_core_roles": []})
        text = fbp.render_progress_text(view)
        elapsed = time.perf_counter() - start
        self.assertEqual(8, len(view["phases"]))
        self.assertIn("Next actions", text)
        self.assertLess(elapsed, 0.5)

    def test_progress_docs_refs_stay_canonical_and_bounded(self) -> None:
        policy = fbp.load_policy(ROOT / "configs" / "firstboot-progress-view-policy.json")
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
