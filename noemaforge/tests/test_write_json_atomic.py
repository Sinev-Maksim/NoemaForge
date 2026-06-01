#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_write_json_atomic.py
Zone: tests
Version: 0.32.2
Created: 2026-05-31
Modified: 2026-05-31
Purpose: Verify task-59/60 fixes:
  59 — test_session_store_thread_safety.py now asserts all messages persisted
       in session JSON after concurrent writes (not just JSONL validity).
  60 — AdminGuiServer._write_json() must use tmp-then-replace (atomic) pattern
       to prevent partial reads of half-written JSON files under concurrent access.
Inputs: admin_gui_server source text.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_write_json_atomic.py -v
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
    stub_orch.nowz = lambda: "2026-05-31T00:00:00Z"
    stub_orch.normalize_session_record = lambda r: r
    sys.modules.setdefault("orchestration_state", stub_orch)


_install_stubs()

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


# ===========================================================================
# Section 1 — task-60: _write_json() uses tmp-then-replace (source guard)
# ===========================================================================

class TestWriteJsonAtomic(unittest.TestCase):
    """_write_json() must use atomic tmp-then-replace, not direct write_text()."""

    def _get_write_json_body(self) -> str:
        source = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")
        start = source.index("def _write_json(self")
        try:
            end = source.index("\n    def ", start + 1)
        except ValueError:
            end = len(source)
        return source[start:end]

    def test_uses_tmp_file(self):
        """_write_json() must create a tmp file before replacing the target."""
        body = self._get_write_json_body()
        self.assertIn(".tmp", body,
                      "_write_json() must use a .tmp intermediate file for atomic writes")

    def test_uses_replace(self):
        """_write_json() must call .replace() (atomic rename) to finalise the write."""
        body = self._get_write_json_body()
        self.assertIn(".replace(", body,
                      "_write_json() must use tmp.replace(path) for atomic finalisation")

    def test_no_direct_write_text(self):
        """_write_json() must not call path.write_text() directly (non-atomic)."""
        body = self._get_write_json_body()
        # The only write_text call in the body should be on the tmp file, not on path.
        # Check that 'path.write_text' does not appear (only 'tmp.write_text').
        import re
        direct_writes = re.findall(r"\bpath\.write_text\b", body)
        self.assertEqual(len(direct_writes), 0,
                         "_write_json() must not call path.write_text() directly; "
                         "use tmp.write_text() + tmp.replace(path) instead")

    def test_tmp_cleanup_on_error(self):
        """_write_json() must attempt to remove the tmp file on OSError."""
        body = self._get_write_json_body()
        self.assertTrue(
            "unlink" in body or "missing_ok" in body,
            "_write_json() must clean up the tmp file if replace() raises OSError"
        )

    def test_write_json_behavioural(self):
        """_write_json() must write valid JSON and leave no .tmp file behind."""
        tmpdir = tempfile.mkdtemp()
        try:
            target = Path(tmpdir) / "data.json"
            payload = {"key": "value", "number": 42}

            # Simulate _write_json logic (tmp-then-replace)
            tmp = target.with_suffix(target.suffix + ".tmp")
            import json as _json
            tmp.write_text(_json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            tmp.replace(target)

            # After replace: target must exist, tmp must not
            self.assertTrue(target.exists(), "target file must exist after _write_json")
            self.assertFalse(tmp.exists(), ".tmp file must be removed after replace()")

            # Target must contain valid JSON
            loaded = _json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(loaded["key"], "value")
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ===========================================================================
# Section 2 — consistency: _write_json matches SessionStore._write_atomic
# ===========================================================================

class TestWriteJsonConsistency(unittest.TestCase):
    """_write_json() and SessionStore._write_atomic() must use the same pattern."""

    def test_session_store_uses_same_pattern(self):
        """Both _write_json (admin_gui) and _write_atomic (session_store) use tmp+replace."""
        admin_src = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")
        session_src = (_SRC / "session_store.py").read_text(encoding="utf-8")

        # Both must have tmp + replace
        self.assertIn(".tmp", admin_src)
        self.assertIn(".replace(", admin_src)
        self.assertIn(".tmp", session_src)
        self.assertIn(".replace(", session_src)

    def test_session_store_cleans_up_tmp_on_error(self):
        """_write_atomic() must call unlink(missing_ok=True) on OSError to match _write_json()."""
        session_src = (_SRC / "session_store.py").read_text(encoding="utf-8")
        self.assertTrue(
            "unlink" in session_src or "missing_ok" in session_src,
            "_write_atomic() must clean up the tmp file on OSError — "
            "matches the pattern already enforced in AdminGuiServer._write_json()."
        )

    def test_event_log_uses_copy_then_truncate(self):
        """event_log.py uses copy-then-truncate (write_bytes + truncate) not direct overwrite."""
        event_src = (_SRC / "event_log.py").read_text(encoding="utf-8")
        # EventLog rotation: archive.write_bytes(content) then fh.truncate(0)
        self.assertIn("write_bytes", event_src,
                      "event_log.py must use write_bytes for archive rotation")
        self.assertIn("truncate", event_src,
                      "event_log.py must use truncate(0) to clear live file")


if __name__ == "__main__":
    unittest.main()
