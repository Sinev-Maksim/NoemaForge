#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_status_comment_accuracy.py
Zone: tests
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: Verify that EventLog.status() docstring accurately describes the
         lock-boundary of each field (rotation_count protected, current_size_bytes
         is a best-effort sample outside the lock) and that the behaviour matches
         the documentation.
Inputs: EventLog from event_log; temporary directories.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_status_comment_accuracy.py -v
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
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

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
# Section 1 — Docstring accuracy: correct claim about lock boundary
# ===========================================================================

class TestStatusDocstringAccuracy(unittest.TestCase):
    """status() docstring must accurately state which fields are lock-protected."""

    _SRC_FILE = _SRC / "event_log.py"

    def _get_status_docstring(self) -> str:
        source = self._SRC_FILE.read_text(encoding="utf-8")
        method_start = source.index("def status(self)")
        doc_start = source.index('"""', method_start)
        doc_end = source.index('"""', doc_start + 3) + 3
        return source[doc_start:doc_end]

    def _get_status_comment(self) -> str:
        """Extract the inline comment block inside status() before 'with self._lock'."""
        source = self._SRC_FILE.read_text(encoding="utf-8")
        method_start = source.index("def status(self)")
        lock_line = source.index("with self._lock:", method_start)
        return source[method_start:lock_line]

    def test_docstring_does_not_claim_full_consistency(self):
        """status() docstring must NOT claim both fields are consistent in one snapshot."""
        doc = self._get_status_docstring()
        # Old misleading claim: "to ensure consistency between the two counters"
        self.assertNotIn("consistency between the two counters", doc,
                         "Old misleading 'consistency between counters' claim must be removed")

    def test_docstring_explicitly_states_size_outside_lock(self):
        """status() docstring must state current_size_bytes is sampled outside the lock."""
        doc = self._get_status_docstring()
        self.assertTrue(
            "outside" in doc.lower() or "not guaranteed" in doc.lower() or "best-effort" in doc.lower(),
            "Docstring must explicitly state current_size_bytes is sampled outside self._lock"
        )

    def test_docstring_acknowledges_inconsistency_risk(self):
        """status() docstring must acknowledge the snapshot can be inconsistent."""
        doc = self._get_status_docstring()
        # Accept any phrasing that conveys the inconsistency risk.
        phrases = [
            "inconsistent",
            "not consistent",
            "may not be consistent",
            "not guaranteed to be consistent",
            "may not be consistent",
        ]
        self.assertTrue(
            any(p in doc.lower() for p in phrases),
            "Docstring must acknowledge size/rotation_count may not be consistent; "
            f"checked phrases: {phrases}"
        )

    def test_rotation_count_described_as_lock_protected(self):
        """Docstring must note rotation_count IS protected by the lock."""
        doc = self._get_status_docstring()
        # The field or its lock-protection should be documented
        self.assertIn("rotation_count", doc)
        self.assertTrue(
            "_lock" in doc or "lock" in doc.lower(),
            "Docstring should mention lock protection for rotation_count"
        )

    def test_process_restart_caveat_documented(self):
        """Docstring must note rotation_count resets on each process restart."""
        doc = self._get_status_docstring()
        self.assertTrue(
            "restart" in doc.lower() or "process start" in doc.lower(),
            "Docstring must document that rotation_count resets on process restart"
        )

    def test_inline_comment_explains_size_outside_lock(self):
        """The inline comment before 'with self._lock' must explain why size is outside the lock."""
        body = self._get_status_comment()
        self.assertTrue(
            "outside" in body.lower() or "intentionally" in body.lower() or "performance" in body.lower(),
            "Inline comment should explain that size is sampled outside the lock for performance"
        )


# ===========================================================================
# Section 2 — Behavioural verification: lock only wraps _rotation_count
# ===========================================================================

class TestStatusLockBoundary(unittest.TestCase):
    """Verify that the lock is only held when reading _rotation_count, not for stat()."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir)
        self.log = EventLog(root=self._root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_status_does_not_hold_lock_during_stat(self):
        """stat() in status() is called outside the lock — the lock must be free during it."""
        lock_held_at_stat = []

        original_stat = Path.stat

        def spy_stat(self_path, *args, **kwargs):
            # Record whether the log's _lock is held when stat() is called
            lock_held_at_stat.append(self.log._lock.locked())
            return original_stat(self_path, *args, **kwargs)

        self.log.append("test.event", {})
        with patch.object(Path, "stat", spy_stat):
            _ = self.log.status()

        # At least one stat() call should have happened; none should hold the lock
        self.assertTrue(len(lock_held_at_stat) > 0, "stat() must be called during status()")
        # The lock should NOT be held when stat() runs (it's intentionally outside)
        self.assertFalse(any(lock_held_at_stat),
                         "self._lock must NOT be held when stat() is called in status()")

    def test_rotation_count_read_under_lock(self):
        """_rotation_count must be read inside 'with self._lock' in status() source."""
        # _thread.lock.acquire is read-only on CPython/Windows — we verify via
        # source inspection instead of patching.
        source = (_SRC / "event_log.py").read_text(encoding="utf-8")
        method_start = source.index("def status(self)")
        # Find 'with self._lock' inside status()
        try:
            lock_block_start = source.index("with self._lock:", method_start)
        except ValueError:
            self.fail("status() must contain 'with self._lock:' block")
        # Ensure _rotation_count access appears INSIDE that block
        rotation_access = source.index("_rotation_count", lock_block_start)
        # Find the end of the with-block (next line at same or lower indent)
        lock_block_end = source.index("return {", lock_block_start)
        self.assertLess(rotation_access, lock_block_end,
                        "_rotation_count must be read inside the 'with self._lock:' block")

    def test_status_returns_correct_rotation_count(self):
        """rotation_count in status() must match the internal counter."""
        self.assertEqual(self.log.status()["rotation_count"], 0)
        # Simulate two rotations
        self.log._rotation_count = 2
        self.assertEqual(self.log.status()["rotation_count"], 2)

    def test_snapshot_inconsistency_is_possible(self):
        """Demonstrate the documented race: size can be pre-rotation while
        rotation_count is post-rotation in the same status() call."""
        import json as _json

        # Build a scenario: get the pre-rotation size, then trigger rotation,
        # then snapshot status() with a patched stat() that returns the pre-rotation size.
        _fast_path = 1024 * 1024
        line = (_json.dumps({"event": "test", "data": "x" * 80}) + "\n").encode("utf-8")
        count = max(10_001, (_fast_path // len(line)) + 1)
        pre_rotation_content = line * count
        self.log.path.write_bytes(pre_rotation_content)
        pre_rotation_size = len(pre_rotation_content)

        # Simulate: rotation just completed (counter at 1, file at 0 bytes),
        # but our spy returns the pre-rotation size to demonstrate the inconsistency.
        with self.log._lock:
            self.log._maybe_rotate()
        # File is now 0 bytes after rotation
        self.assertEqual(self.log.path.stat().st_size, 0)
        self.assertEqual(self.log._rotation_count, 1)

        # Patch stat() to return the stale pre-rotation size (as if called just before truncation)
        from unittest.mock import MagicMock
        fake_stat = MagicMock()
        fake_stat.st_size = pre_rotation_size

        original_stat = Path.stat
        call_count = [0]

        def stale_stat(self_path, *args, **kwargs):
            if "events.jsonl" in self_path.name:
                call_count[0] += 1
                return fake_stat
            return original_stat(self_path, *args, **kwargs)

        with patch.object(Path, "stat", stale_stat):
            s = self.log.status()

        # Demonstrate: rotation_count=1 (post-rotation) but size=pre_rotation_size
        self.assertEqual(s["rotation_count"], 1, "rotation_count should be post-rotation")
        self.assertEqual(s["current_size_bytes"], pre_rotation_size,
                         "Stale stat returns pre-rotation size — inconsistency is expected and documented")


if __name__ == "__main__":
    unittest.main()
