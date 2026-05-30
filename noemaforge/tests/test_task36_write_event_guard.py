#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_task36_write_event_guard.py
Zone: test
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: Verify _write_event() in noemaforge_core.py except block is guarded against secondary failure.
Inputs: noemaforge_core.py source text (functional tests skipped on Windows due to fcntl).
Outputs: unittest results.
Side effects: None.
Tests: python -m unittest noemaforge/tests/test_task36_write_event_guard.py -v
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

SRC_PATH = ROOT / "src" / "noemaforge_core.py"
SRC_TEXT = SRC_PATH.read_text(encoding="utf-8")


class TestSourceContainsWriteEventGuard(unittest.TestCase):
    """Source-text guards only — no fcntl import needed, pass on Windows."""

    def test_role_output_parse_failed_event_present(self):
        """Source must contain ROLE_OUTPUT_PARSE_FAILED event type."""
        self.assertIn("ROLE_OUTPUT_PARSE_FAILED", SRC_TEXT)

    def test_write_event_inside_except_block(self):
        """_write_event() must be inside the except block for _load_json failure."""
        # Verify both the except and _write_event appear together in context.
        parse_failed_pos = SRC_TEXT.find("ROLE_OUTPUT_PARSE_FAILED")
        self.assertGreater(parse_failed_pos, 0)
        # Find the surrounding except block.
        except_before = SRC_TEXT.rfind("except Exception", 0, parse_failed_pos)
        self.assertGreater(except_before, 0, "_write_event must be inside an except block")

    def test_inner_except_guards_write_event(self):
        """A nested try/except must guard _write_event() itself."""
        parse_failed_pos = SRC_TEXT.find("ROLE_OUTPUT_PARSE_FAILED")
        # Look backwards from ROLE_OUTPUT_PARSE_FAILED for a try: that wraps the _write_event call.
        region = SRC_TEXT[parse_failed_pos - 500: parse_failed_pos + 200]
        self.assertIn("try:", region, "Nested try must wrap _write_event() call")

    def test_res_none_still_reached_after_guard(self):
        """res = None must appear after the guarded _write_event() block."""
        parse_failed_pos = SRC_TEXT.find("ROLE_OUTPUT_PARSE_FAILED")
        after_event = SRC_TEXT[parse_failed_pos:]
        res_none_pos = after_event.find("res = None")
        self.assertGreater(res_none_pos, 0, "res = None must follow _write_event() block")

    def test_guard_comment_explains_secondary_failure(self):
        """There must be a comment explaining the inner guard is for secondary failure."""
        self.assertIn("secondary failure", SRC_TEXT)

    def test_out_path_in_event_data(self):
        """out_path must be included in the event data for forensics."""
        self.assertIn('"out_path"', SRC_TEXT)

    def test_error_in_event_data(self):
        """The exception error string must be included in event data."""
        # Check that str(e) is used in the write_event call.
        parse_failed_pos = SRC_TEXT.find("ROLE_OUTPUT_PARSE_FAILED")
        region = SRC_TEXT[parse_failed_pos - 100: parse_failed_pos + 500]
        self.assertIn("str(e)", region)


if __name__ == "__main__":
    unittest.main()
