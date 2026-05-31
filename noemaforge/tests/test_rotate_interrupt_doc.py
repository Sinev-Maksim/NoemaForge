#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_rotate_interrupt_doc.py
Zone: tests
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: Verify that _maybe_rotate() docstring documents the KeyboardInterrupt /
         SystemExit half-rotation risk, explains why except OSError is intentionally
         narrow, and describes the accepted worst-case duplicate-archive scenario.
Inputs: EventLog from event_log; source text of event_log.py.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_rotate_interrupt_doc.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


def _install_stubs() -> None:
    stub_ver = types.ModuleType("noemaforge_version")
    stub_ver.RUNTIME_VERSION = "0.32.2"
    sys.modules.setdefault("noemaforge_version", stub_ver)

    stub_orch = types.ModuleType("orchestration_state")
    stub_orch.nowz = lambda: "2026-05-30T00:00:00Z"
    sys.modules.setdefault("orchestration_state", stub_orch)


_install_stubs()

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from event_log import EventLog  # noqa: E402


# ===========================================================================
# Helpers
# ===========================================================================

def _get_maybe_rotate_docstring() -> str:
    source = (_SRC / "event_log.py").read_text(encoding="utf-8")
    method_start = source.index("def _maybe_rotate(self)")
    doc_start = source.index('"""', method_start)
    doc_end = source.index('"""', doc_start + 3) + 3
    return source[doc_start:doc_end]


def _get_full_source() -> str:
    return (_SRC / "event_log.py").read_text(encoding="utf-8")


# ===========================================================================
# Section 1 — Docstring completeness: must document the half-rotation risk
# ===========================================================================

class TestMaybeRotateDocstringCompleteness(unittest.TestCase):

    def setUp(self):
        self.doc = _get_maybe_rotate_docstring()

    def test_keyboardinterrupt_mentioned(self):
        """_maybe_rotate() docstring must mention KeyboardInterrupt."""
        self.assertIn("KeyboardInterrupt", self.doc,
                      "_maybe_rotate() docstring must mention KeyboardInterrupt risk")

    def test_systemexit_mentioned(self):
        """_maybe_rotate() docstring must mention SystemExit."""
        self.assertIn("SystemExit", self.doc,
                      "_maybe_rotate() docstring must mention SystemExit risk")

    def test_except_oserror_intentional_explained(self):
        """Docstring must explain that catching only OSError is intentional."""
        self.assertTrue(
            "intentional" in self.doc.lower() or "only" in self.doc.lower(),
            "Docstring must explain that except OSError is intentionally narrow"
        )

    def test_half_rotation_consequence_documented(self):
        """Docstring must describe the duplicate-archive consequence of a half-rotation."""
        self.assertTrue(
            "duplicate" in self.doc.lower()
            or "both" in self.doc.lower()
            or "same content" in self.doc.lower()
            or "archive" in self.doc.lower(),
            "Docstring must describe what happens (duplicate archive) on half-rotation"
        )

    def test_live_file_preserved_stated(self):
        """Docstring must state that the live file is always preserved on non-OSError."""
        self.assertTrue(
            "intact" in self.doc.lower()
            or "preserved" in self.doc.lower()
            or "no data" in self.doc.lower()
            or "live file" in self.doc.lower(),
            "Docstring must state the live file is always preserved"
        )

    def test_accepted_risk_documented(self):
        """Docstring must document that this is an accepted (design) decision."""
        self.assertTrue(
            "accepted" in self.doc.lower()
            or "accept" in self.doc.lower()
            or "harmless" in self.doc.lower()
            or "worst-case" in self.doc.lower(),
            "Docstring must state the risk is accepted with rationale"
        )


# ===========================================================================
# Section 2 — Source guard: except clause is OSError (not bare except or Exception)
# ===========================================================================

class TestExceptClauseIsNarrow(unittest.TestCase):
    """_maybe_rotate() must use 'except OSError' not 'except Exception' or bare except."""

    def _get_maybe_rotate_body(self) -> str:
        source = _get_full_source()
        method_start = source.index("def _maybe_rotate(self)")
        # Find the next method definition to bound the body
        try:
            method_end = source.index("\n    def ", method_start + 1)
        except ValueError:
            method_end = len(source)
        return source[method_start:method_end]

    def test_except_oserror_present(self):
        """_maybe_rotate() must contain 'except OSError'."""
        body = self._get_maybe_rotate_body()
        self.assertIn("except OSError", body)

    def test_no_bare_except_in_rotate(self):
        """_maybe_rotate() must not use a bare 'except:' clause."""
        body = self._get_maybe_rotate_body()
        # A bare except looks like 'except:' or 'except :'
        import re
        bare_excepts = re.findall(r"\bexcept\s*:", body)
        self.assertEqual(len(bare_excepts), 0,
                         "No bare 'except:' in _maybe_rotate() — only OSError should be caught")

    def test_no_except_baseexception(self):
        """_maybe_rotate() must not catch BaseException."""
        body = self._get_maybe_rotate_body()
        self.assertNotIn("except BaseException", body,
                         "_maybe_rotate() must not catch BaseException")


# ===========================================================================
# Section 3 — Behavioural: half-rotation leaves live file intact
# ===========================================================================

class TestHalfRotationBehaviour(unittest.TestCase):
    """After a simulated half-rotation (archive written, truncate skipped),
    the live file must still contain the original content."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir)
        self.log = EventLog(root=self._root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_rotation_content(self) -> bytes:
        line = (json.dumps({"event": "test", "data": "x" * 80}) + "\n").encode("utf-8")
        count = max(10_001, (1024 * 1024 // len(line)) + 1)
        content = line * count
        self.log.path.write_bytes(content)
        return content

    def test_live_file_intact_if_truncate_skipped(self):
        """If truncation is skipped (simulating an interrupt), live file content survives."""
        from unittest.mock import patch
        from pathlib import Path as _Path

        original_content = self._write_rotation_content()

        # WindowsPath instance attributes are read-only — patch at the class level.
        # _patched_open intercepts only `live_path.open("r+b")` (the truncation
        # call in _maybe_rotate step 4).  All other Path.open calls (archive
        # write_bytes uses "wb", read_bytes uses "rb") go through the real open.
        live_path = self.log.path
        _real_open = _Path.open

        class FakeFH:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def truncate(self, size=0): raise KeyboardInterrupt("simulated")

        def _patched_open(path_self, mode='r', *a, **kw):
            if path_self == live_path and mode == 'r+b':
                return FakeFH()
            return _real_open(path_self, mode, *a, **kw)

        with patch.object(_Path, 'open', _patched_open):
            try:
                with self.log._lock:
                    self.log._maybe_rotate()
            except KeyboardInterrupt:
                pass

        # Live file must still have the original content
        self.assertEqual(self.log.path.read_bytes(), original_content,
                         "Live file must be intact after a half-rotation (truncate skipped)")

    def test_archive_written_before_interrupt(self):
        """The .1 archive must exist after a half-rotation (archive write succeeded)."""
        from unittest.mock import patch
        from pathlib import Path as _Path

        self._write_rotation_content()

        live_path = self.log.path
        _real_open = _Path.open

        class FakeFH:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def truncate(self, size=0): raise KeyboardInterrupt("simulated")

        def _patched_open(path_self, mode='r', *a, **kw):
            if path_self == live_path and mode == 'r+b':
                return FakeFH()
            return _real_open(path_self, mode, *a, **kw)

        with patch.object(_Path, 'open', _patched_open):
            try:
                with self.log._lock:
                    self.log._maybe_rotate()
            except KeyboardInterrupt:
                pass

        archive = EventLog._archive_path(self.log.path, 1)
        self.assertTrue(archive.exists(),
                        ".1 archive should have been written before the truncate interrupt")


if __name__ == "__main__":
    unittest.main()
