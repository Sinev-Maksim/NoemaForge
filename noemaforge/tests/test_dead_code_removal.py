#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_dead_code_removal.py
Zone: tests
Version: 0.32.2
Created: 2026-05-31
Modified: 2026-05-31
Purpose: Guard against re-introduction of the dead-code bugs fixed in task-63:
           1. Duplicate session_current() definition in AdminGuiServer — the first
              definition (no-arg, no try/except) was silently overridden by a second
              definition with session_id param.  Python uses the LAST definition;
              the first was dead code.
           2. Duplicate POST /api/session/mode handler in do_POST — the second
              `if path == "/api/session/mode":` block was unreachable because the
              first handler already returns.  The dead handler lacked composite_top_n
              validation and would have called session_set_mode() instead of
              session_mode(), producing a different response shape.
         Tests are source-text guards: they detect if someone re-introduces the
         duplicates by adding a version-controlled assertion about count.
Inputs: admin_gui_server.py source text.
Outputs: pytest pass/fail.
Side effects: None (read-only source inspection).
Tests: python3 -m unittest noemaforge/tests/test_dead_code_removal.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


class TestDeadCodeRemoval(unittest.TestCase):
    """Guard that dead duplicate methods/routes stay removed from admin_gui_server.py."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._source = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Bug 1: duplicate session_current() definition
    # ------------------------------------------------------------------

    def test_session_current_defined_exactly_once(self) -> None:
        """AdminGuiServer must have exactly ONE session_current() definition."""
        defs = re.findall(r"^\s*def session_current\b", self._source, re.MULTILINE)
        self.assertEqual(
            len(defs), 1,
            f"session_current() must be defined exactly once; found {len(defs)} definitions. "
            "A duplicate zero-arg definition at the top of the session-state section "
            "is dead code (Python uses the last definition).",
        )

    def test_session_current_has_session_id_param(self) -> None:
        """The single session_current() definition must accept a session_id parameter."""
        match = re.search(r"def session_current\(self,\s*session_id", self._source)
        self.assertIsNotNone(
            match,
            "session_current() must accept session_id parameter (with default='default'). "
            "A bare def session_current(self) with no session_id was the dead version.",
        )

    def test_session_current_has_try_except(self) -> None:
        """The session_current() body must include a try/except for error safety."""
        # Find the method body
        start = self._source.index("def session_current(self, session_id")
        # Read the next ~200 chars for the body
        body = self._source[start: start + 300]
        self.assertIn("try:", body,
                      "session_current() must have a try/except block for error safety; "
                      "the old dead version had none.")

    # ------------------------------------------------------------------
    # Bug 2: duplicate POST /api/session/mode handler in do_POST
    # ------------------------------------------------------------------

    def test_session_mode_route_handled_exactly_once_in_do_post(self) -> None:
        """POST /api/session/mode must be handled by exactly ONE if-block in do_POST."""
        # Find all occurrences of the route string inside do_POST
        # We count 'if path == "/api/session/mode"' occurrences
        occurrences = re.findall(
            r'if\s+path\s*==\s*"/api/session/mode"', self._source
        )
        self.assertEqual(
            len(occurrences), 1,
            f"POST /api/session/mode must have exactly one handler; "
            f"found {len(occurrences)}. A second unreachable handler after "
            f"'/api/vault/reinventory' was dead code (Python hits the first `return`).",
        )

    def test_live_mode_handler_validates_composite_top_n(self) -> None:
        """The live POST /api/session/mode handler must validate composite_top_n."""
        # Find the handler block
        idx = self._source.index('if path == "/api/session/mode"')
        # Look at ~250 chars of the handler body
        body = self._source[idx: idx + 350]
        self.assertIn("composite_top_n must be an integer", body,
                      "The POST /api/session/mode handler must validate composite_top_n "
                      "and return 400 on non-integer values. The dead second handler "
                      "lacked this validation.")

    def test_live_mode_handler_calls_session_mode(self) -> None:
        """The live POST /api/session/mode handler must call session_mode() not session_set_mode()."""
        idx = self._source.index('if path == "/api/session/mode"')
        body = self._source[idx: idx + 600]
        self.assertIn("session_mode(", body,
                      "The live POST /api/session/mode handler must call server.session_mode(); "
                      "the dead handler called session_set_mode() (different signature).")

    # ------------------------------------------------------------------
    # Regression guard: session_set_mode() still exists independently
    # ------------------------------------------------------------------

    def test_session_set_mode_still_defined(self) -> None:
        """session_set_mode() must still be defined (used by other callers)."""
        self.assertIn("def session_set_mode(self",
                      self._source,
                      "session_set_mode() must remain defined; only the dead do_POST "
                      "handler that called it was removed, not the method itself.")


if __name__ == "__main__":
    unittest.main()
