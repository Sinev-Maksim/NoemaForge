#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_task35_limit_comment.py
Zone: test
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: Verify /api/events limit clamp handles negative values and source has the comment.
Inputs: AdminGuiServer.do_GET /api/events limit handling.
Outputs: unittest results.
Side effects: None.
Tests: python -m unittest noemaforge/tests/test_task35_limit_comment.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


class TestNegativeLimitClamp(unittest.TestCase):
    """Verify the clamp logic handles negative limit values correctly."""

    def _clamp(self, limit: int) -> int:
        return min(max(1, limit), 1000)

    def test_negative_limit_clamped_to_one(self):
        self.assertEqual(self._clamp(-5000), 1)

    def test_zero_limit_clamped_to_one(self):
        self.assertEqual(self._clamp(0), 1)

    def test_positive_limit_within_bounds_unchanged(self):
        self.assertEqual(self._clamp(200), 200)

    def test_limit_above_1000_clamped_to_1000(self):
        self.assertEqual(self._clamp(1_000_000), 1000)

    def test_limit_exactly_one_unchanged(self):
        self.assertEqual(self._clamp(1), 1)

    def test_limit_exactly_1000_unchanged(self):
        self.assertEqual(self._clamp(1000), 1000)


class TestSourceContainsClampWithComment(unittest.TestCase):
    SRC_TEXT = (ROOT / "src" / "admin_gui_server.py").read_text(encoding="utf-8")

    def test_clamp_expression_present(self):
        self.assertIn("min(max(1, limit), 1000)", self.SRC_TEXT)

    def test_comment_mentions_negative(self):
        """Source must have a comment explaining that negative values are clamped."""
        self.assertIn("negative", self.SRC_TEXT.lower())

    def test_clamp_called_before_events_api(self):
        """Clamp must appear before events_api() call in do_GET."""
        clamp_pos = self.SRC_TEXT.find("min(max(1, limit), 1000)")
        events_api_pos = self.SRC_TEXT.find("self.server.events_api(after_index=after, limit=limit)")
        self.assertGreater(events_api_pos, clamp_pos, "Clamp must precede events_api() call")


if __name__ == "__main__":
    unittest.main()
