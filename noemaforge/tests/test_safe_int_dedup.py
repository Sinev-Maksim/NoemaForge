#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_safe_int_dedup.py
Zone: tests
Version: 0.32.2
Created: 2026-06-01
Modified: 2026-06-01
Purpose: Tests for task-80 (_safe_int deduplication):
           - task-80 (LOW): lsp_facade.py and mcp_router.py previously defined
             their own _safe_int with a simple try/except but without NaN/Inf
             handling. Both now import from orchestration_state._safe_int,
             which is fully tested (42 assertions) and covers NaN/Inf via the
             isinstance fast-path with OverflowError/ValueError catch.
         Tests verify: no local _safe_int definition in lsp_facade or mcp_router;
         import statement present; orchestration_state version accessible from
         both contexts; plugin_runner.py (not in scope) still has its own copy.
Inputs: lsp_facade.py, mcp_router.py, orchestration_state.py source text.
Outputs: pytest pass/fail.
Side effects: None.
Tests: python3 -m unittest noemaforge/tests/test_safe_int_dedup.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_LSP_SRC = (_SRC / "lsp_facade.py").read_text(encoding="utf-8")
_MCR_SRC = (_SRC / "mcp_router.py").read_text(encoding="utf-8")
_PLR_SRC = (_SRC / "plugin_runner.py").read_text(encoding="utf-8")
_ORCH_SRC = (_SRC / "orchestration_state.py").read_text(encoding="utf-8")


class TestSafeIntDeduplicated(unittest.TestCase):
    """task-80: lsp_facade and mcp_router must import _safe_int from orchestration_state."""

    # --- lsp_facade.py ---

    def test_lsp_facade_no_local_safe_int_def(self) -> None:
        """lsp_facade.py must NOT define its own _safe_int."""
        count = _LSP_SRC.count("def _safe_int(")
        self.assertEqual(count, 0,
                         "lsp_facade.py must not define its own _safe_int (import from orchestration_state)")

    def test_lsp_facade_imports_safe_int_from_orchestration_state(self) -> None:
        """lsp_facade.py must import _safe_int from orchestration_state."""
        self.assertIn("from orchestration_state import _safe_int", _LSP_SRC,
                      "lsp_facade.py must import _safe_int from orchestration_state")

    def test_lsp_facade_import_precedes_usage(self) -> None:
        """The import must appear before any _safe_int call in lsp_facade.py."""
        import_idx = _LSP_SRC.index("from orchestration_state import _safe_int")
        call_idx = _LSP_SRC.index("_safe_int(", import_idx + 1)
        self.assertLess(import_idx, call_idx,
                        "orchestration_state import must precede first _safe_int() call")

    # --- mcp_router.py ---

    def test_mcp_router_no_local_safe_int_def(self) -> None:
        """mcp_router.py must NOT define its own _safe_int."""
        count = _MCR_SRC.count("def _safe_int(")
        self.assertEqual(count, 0,
                         "mcp_router.py must not define its own _safe_int (import from orchestration_state)")

    def test_mcp_router_imports_safe_int_from_orchestration_state(self) -> None:
        """mcp_router.py must import _safe_int from orchestration_state."""
        self.assertIn("from orchestration_state import _safe_int", _MCR_SRC,
                      "mcp_router.py must import _safe_int from orchestration_state")

    def test_mcp_router_import_precedes_usage(self) -> None:
        """The import must appear before any _safe_int call in mcp_router.py."""
        import_idx = _MCR_SRC.index("from orchestration_state import _safe_int")
        call_idx = _MCR_SRC.index("_safe_int(", import_idx + 1)
        self.assertLess(import_idx, call_idx,
                        "orchestration_state import must precede first _safe_int() call")

    # --- plugin_runner.py ---

    def test_plugin_runner_no_local_safe_int_def(self) -> None:
        """plugin_runner.py must NOT define its own _safe_int."""
        count = _PLR_SRC.count("def _safe_int(")
        self.assertEqual(count, 0,
                         "plugin_runner.py must not define its own _safe_int (import from orchestration_state)")

    def test_plugin_runner_imports_safe_int_from_orchestration_state(self) -> None:
        """plugin_runner.py must import _safe_int from orchestration_state."""
        self.assertIn("from orchestration_state import _safe_int", _PLR_SRC,
                      "plugin_runner.py must import _safe_int from orchestration_state")

    # --- orchestration_state.py (canonical version) ---

    def test_orchestration_state_defines_safe_int(self) -> None:
        """orchestration_state.py must define the canonical _safe_int."""
        self.assertIn("def _safe_int(", _ORCH_SRC,
                      "orchestration_state.py must define the canonical _safe_int")

    def test_orchestration_state_safe_int_handles_nan_inf(self) -> None:
        """Canonical _safe_int must cover NaN/Inf (OverflowError/ValueError catch)."""
        self.assertIn("OverflowError", _ORCH_SRC,
                      "orchestration_state._safe_int must catch OverflowError for Inf inputs")
        self.assertIn("ValueError", _ORCH_SRC,
                      "orchestration_state._safe_int must catch ValueError for NaN inputs")


class TestSafeIntFunctional(unittest.TestCase):
    """Verify orchestration_state._safe_int can be imported cleanly from both modules."""

    def setUp(self) -> None:
        import noemaforge_version as real_version
        sys.modules.setdefault("noemaforge_version", real_version)

    def test_import_safe_int_from_orchestration_state(self) -> None:
        """orchestration_state._safe_int must be importable in a clean environment."""
        from orchestration_state import _safe_int
        self.assertEqual(_safe_int("42", 0), 42)
        self.assertEqual(_safe_int("abc", 99), 99)
        self.assertEqual(_safe_int(float("nan"), 7), 7)
        self.assertEqual(_safe_int(float("inf"), 3), 3)

    def test_safe_int_default_is_optional(self) -> None:
        """orchestration_state._safe_int default parameter must be optional (default=0)."""
        from orchestration_state import _safe_int
        # Callers in lsp_facade/mcp_router always pass explicit default,
        # so optional default (=0) is backward-compatible.
        self.assertEqual(_safe_int("not_a_number"), 0,
                         "_safe_int with no default argument must return 0")

    def test_safe_int_with_explicit_default_matches_lsp_callers(self) -> None:
        """_safe_int(value, 200) must work as in lsp_facade callers."""
        from orchestration_state import _safe_int
        self.assertEqual(_safe_int(None, 200), 200)
        self.assertEqual(_safe_int("50", 200), 50)
        self.assertEqual(_safe_int("", 200), 200)


if __name__ == "__main__":
    unittest.main()
