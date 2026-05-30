#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_atomic_write_json.py
Zone: test
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: TDD tests for AdminGuiServer._write_json() atomic tmp-then-rename pattern.
  Verifies that _write_json uses a sibling .tmp file before renaming to the target,
  so concurrent readers never observe a partial/truncated JSON file.
  Matches the pattern already used by SessionStore._write_atomic().
Inputs: admin_gui_server.AdminGuiServer._write_json().
Outputs: test pass/fail.
Side effects: Creates and removes temporary directories.
Tests: python noemaforge/tests/test_atomic_write_json.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from admin_gui_server import AdminGuiServer  # noqa: E402
from session_store import SessionStore  # noqa: E402
from event_log import EventLog  # noqa: E402


def _make_server(td: Path) -> AdminGuiServer:
    """Minimal AdminGuiServer stub with real file I/O."""
    srv = object.__new__(AdminGuiServer)
    srv.data_root = td
    srv.gui_state_dir = td / "gui"
    srv.gui_state_dir.mkdir(parents=True, exist_ok=True)
    srv.jobs_dir = td / "jobs"
    srv.jobs_dir.mkdir(parents=True, exist_ok=True)
    srv.review_dir = td / "review"
    (srv.review_dir / "sr" / "inbox").mkdir(parents=True, exist_ok=True)
    (srv.review_dir / "ssr" / "inbox").mkdir(parents=True, exist_ok=True)
    srv.model_selection_state = td / "model_selection"
    srv.model_selection_state.mkdir(parents=True, exist_ok=True)
    srv.session_store = SessionStore(td / "sessions")
    srv.event_log = EventLog(td / "events")
    srv._state_lock = threading.Lock()
    return srv


class TestWriteJsonAtomicBehavior(unittest.TestCase):
    """_write_json() must produce a valid JSON file and leave no .tmp artifact."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.srv = _make_server(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_target_file_created(self) -> None:
        """_write_json creates the target file."""
        target = self.td / "gui" / "test.json"
        self.srv._write_json(target, {"key": "value"})
        self.assertTrue(target.exists())

    def test_target_file_valid_json(self) -> None:
        """Written file contains valid JSON matching the input object."""
        target = self.td / "gui" / "out.json"
        self.srv._write_json(target, {"a": 1, "b": [1, 2, 3]})
        loaded = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(loaded, {"a": 1, "b": [1, 2, 3]})

    def test_no_tmp_file_left_after_write(self) -> None:
        """No .tmp sibling remains after a successful write."""
        target = self.td / "gui" / "state.json"
        self.srv._write_json(target, {"x": 42})
        tmp = target.with_suffix(target.suffix + ".tmp")
        self.assertFalse(tmp.exists(), ".tmp file should be renamed away after write")

    def test_parent_dir_created_if_missing(self) -> None:
        """_write_json creates intermediate directories automatically."""
        target = self.td / "deep" / "nested" / "file.json"
        self.srv._write_json(target, {})
        self.assertTrue(target.exists())

    def test_overwrites_existing_file(self) -> None:
        """Repeated calls overwrite the previous content atomically."""
        target = self.td / "gui" / "overwrite.json"
        self.srv._write_json(target, {"v": 1})
        self.srv._write_json(target, {"v": 2})
        loaded = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(loaded["v"], 2)

    def test_uses_tmp_rename_pattern(self) -> None:
        """Write goes through a .tmp path before rename (sequence check via spy)."""
        target = self.td / "gui" / "spy_target.json"
        write_calls = []

        orig_write_text = Path.write_text

        def spy_write_text(self_path, data, encoding=None, errors=None):
            write_calls.append(str(self_path))
            return orig_write_text(self_path, data, encoding=encoding or "utf-8")

        with patch.object(Path, "write_text", spy_write_text):
            self.srv._write_json(target, {"spy": True})

        # The write must have gone to a .tmp path, not directly to the target.
        self.assertTrue(
            any(".tmp" in p for p in write_calls),
            f"Expected a .tmp write; got: {write_calls}",
        )
        # The final target must exist and be valid JSON.
        self.assertTrue(target.exists())
        loaded = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(loaded, {"spy": True})

    def test_concurrent_writes_produce_valid_json(self) -> None:
        """Multiple threads writing to the same path each leave valid JSON in the file.

        On Linux the rename(2) syscall guarantees atomicity; on Windows (MoveFileEx)
        a concurrent rename may raise a transient PermissionError — this is a known
        Windows limitation irrelevant to the production host (BigBro-BOS / Linux).
        The test asserts that after all threads finish, the file contains valid JSON
        regardless of how many writes succeeded.
        """
        import platform
        target = self.td / "gui" / "concurrent.json"
        errors: list = []

        def writer(i: int) -> None:
            try:
                self.srv._write_json(target, {"writer": i, "payload": list(range(100))})
            except PermissionError:
                # Windows-only: transient MoveFileEx race; acceptable on dev platform.
                pass
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Unexpected (non-PermissionError) writer exceptions: {errors}")
        # File must contain valid JSON after all writes settle.
        if target.exists():
            content = target.read_text(encoding="utf-8")
            loaded = json.loads(content)
            self.assertIn("writer", loaded)


class TestSourceContainsAtomicPattern(unittest.TestCase):
    """Source-text assertions: _write_json must use the tmp-then-replace pattern."""

    def setUp(self) -> None:
        src_path = Path(__file__).parent.parent / "src" / "admin_gui_server.py"
        self._src = src_path.read_text(encoding="utf-8")

    def _write_json_body(self) -> str:
        start = self._src.index("def _write_json(")
        end = self._src.index("\n    def ", start + 1)
        return self._src[start:end]

    def test_uses_tmp_suffix_in_name(self) -> None:
        """_write_json builds a .tmp path (tmp name contains '.tmp')."""
        body = self._write_json_body()
        self.assertIn(".tmp", body)

    def test_uses_replace_for_rename(self) -> None:
        """`tmp.replace(path)` atomic rename is present."""
        body = self._write_json_body()
        self.assertIn(".replace(path)", body)

    def test_no_direct_path_write_text(self) -> None:
        """Direct `path.write_text(...)` is not used (was the non-atomic path)."""
        body = self._write_json_body()
        self.assertNotIn("path.write_text(", body)

    def test_tmp_write_text_present(self) -> None:
        """The tmp path is written via write_text before rename."""
        body = self._write_json_body()
        self.assertIn("tmp.write_text(", body)

    def test_thread_unique_tmp_name(self) -> None:
        """_write_json uses threading.get_ident() for a unique-per-thread tmp name."""
        body = self._write_json_body()
        self.assertIn("threading.get_ident()", body)


if __name__ == "__main__":
    unittest.main()
