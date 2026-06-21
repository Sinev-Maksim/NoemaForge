#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_wiki_check_index_order.py
Zone: test
Version: 0.33.0
Created: 2026-06-18
Modified: 2026-06-18
Purpose: Regression test locking the portable (codepoint / ordinal) ordering of the
  generated wiki hub index in ci/wiki_check.py. Path ordering is case-insensitive on
  Windows but case-sensitive on Linux, so the index must sort by the posix relpath
  string (codepoint), never case-folded, or the hub index goes platform-dependent
  (stale on CI when written locally).
Inputs: ci/wiki_check.wiki_pages with WIKI pointed at a temp mixed-case tree.
Outputs: test pass/fail.
Side effects: Creates and removes a temporary wiki tree; restores wiki_check.WIKI.
Tests: python3 -m unittest noemaforge/tests/test_wiki_check_index_order.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

# ci/wiki_check.py lives at the repo root's ci/ dir.
_CI = Path(__file__).resolve().parents[2] / "ci"
if str(_CI) not in sys.path:
    sys.path.insert(0, str(_CI))

import wiki_check  # noqa: E402


class TestWikiCheckIndexOrder(unittest.TestCase):
    """wiki_pages() must order by codepoint, identically on every platform."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self._wiki = Path(self._td.name) / "wiki"
        (self._wiki / "cat").mkdir(parents=True)
        # Mixed-case names whose codepoint order (uppercase < lowercase) differs
        # from case-insensitive order, so a regression is observable.
        for name in ("apple.md", "Banana.md", "Zebra.md", "aardvark.md"):
            (self._wiki / "cat" / name).write_text("# x\n", encoding="utf-8")
        self._orig_wiki = wiki_check.WIKI
        wiki_check.WIKI = self._wiki

    def tearDown(self) -> None:
        wiki_check.WIKI = self._orig_wiki
        self._td.cleanup()

    def _rels(self) -> list[str]:
        return [p.relative_to(self._wiki).as_posix() for p in wiki_check.wiki_pages()]

    def test_pages_are_codepoint_sorted(self) -> None:
        rels = self._rels()
        # Locked behavior: deterministic codepoint (ordinal) order, identical on
        # Windows and Linux. Uppercase precedes lowercase.
        self.assertEqual(rels, sorted(rels))

    def test_ordering_is_not_case_insensitive(self) -> None:
        rels = self._rels()
        # Guard against a regression to case-folded sorting, which would reorder
        # these mixed-case names and make the generated hub index platform-dependent.
        self.assertNotEqual(rels, sorted(rels, key=str.casefold))

    def test_concrete_expected_order(self) -> None:
        # 'B'(66) < 'Z'(90) < 'a'(97); 'aardvark' < 'apple' ('a' < 'p').
        self.assertEqual(
            self._rels(),
            ["cat/Banana.md", "cat/Zebra.md", "cat/aardvark.md", "cat/apple.md"],
        )


if __name__ == "__main__":
    unittest.main()
