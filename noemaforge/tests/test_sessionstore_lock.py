#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_sessionstore_lock.py
Zone: test
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: TDD tests for SessionStore thread-safety (threading.Lock on R-M-W cycles).
  Verifies that concurrent append_message() and update() calls for the same session
  never lose messages, and that _write_atomic() uses thread-unique tmp names.
  Before this fix, two concurrent threads would each load the old session, each
  append a message, and then both write back — the last writer silently dropped
  the first writer's message.
Inputs: session_store.SessionStore.
Outputs: test pass/fail.
Side effects: Creates and removes temporary directories.
Tests: python noemaforge/tests/test_sessionstore_lock.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from session_store import SessionStore  # noqa: E402


class TestSessionStoreLockAttributes(unittest.TestCase):
    """SessionStore must expose a threading.Lock on self._lock."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.store = SessionStore(Path(self._td.name) / "sessions")

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_has_lock_attribute(self) -> None:
        """SessionStore.__init__ must create self._lock."""
        self.assertTrue(hasattr(self.store, "_lock"))

    def test_lock_is_threading_lock(self) -> None:
        """self._lock must be a threading.Lock (acquire/release interface)."""
        lock = self.store._lock
        self.assertTrue(hasattr(lock, "acquire"))
        self.assertTrue(hasattr(lock, "release"))
        self.assertTrue(hasattr(lock, "__enter__"))
        self.assertTrue(hasattr(lock, "__exit__"))

    def test_lock_is_initially_unlocked(self) -> None:
        """Fresh lock can be acquired immediately."""
        acquired = self.store._lock.acquire(blocking=False)
        if acquired:
            self.store._lock.release()
        self.assertTrue(acquired)


class TestConcurrentAppendMessage(unittest.TestCase):
    """Concurrent append_message() calls must not drop messages."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.store = SessionStore(Path(self._td.name) / "sessions")

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_concurrent_appends_preserve_all_messages(self) -> None:
        """20 threads each appending 1 message → exactly 20 messages in session."""
        n_threads = 20
        errors: list = []

        def appender(i: int) -> None:
            try:
                self.store.append_message("default", {"text": f"msg-{i}", "role": "user"})
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=appender, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Thread exceptions: {errors}")
        session = self.store.load("default")
        messages = session.get("messages", [])
        self.assertEqual(
            len(messages),
            n_threads,
            f"Expected {n_threads} messages, got {len(messages)} — some were lost (RMW race)",
        )

    def test_concurrent_appends_all_message_ids_unique(self) -> None:
        """No two threads should write a message with the same text."""
        n_threads = 10
        errors: list = []

        def appender(i: int) -> None:
            try:
                self.store.append_message("default", {"text": f"unique-{i}", "role": "user"})
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=appender, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        session = self.store.load("default")
        texts = {m.get("text") for m in session.get("messages", [])}
        expected = {f"unique-{i}" for i in range(n_threads)}
        self.assertEqual(texts, expected, f"Missing messages: {expected - texts}")

    def test_sequential_appends_all_preserved(self) -> None:
        """Sanity: sequential appends within max_messages all survive."""
        for i in range(5):
            self.store.append_message("default", {"text": f"seq-{i}", "role": "user"})
        session = self.store.load("default")
        self.assertEqual(len(session.get("messages", [])), 5)


class TestConcurrentUpdate(unittest.TestCase):
    """Concurrent update() calls must not corrupt session data."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.store = SessionStore(Path(self._td.name) / "sessions")

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_concurrent_updates_produce_valid_session(self) -> None:
        """10 concurrent update() calls → session file is valid after all complete."""
        errors: list = []

        def updater(i: int) -> None:
            try:
                self.store.update("default", selected_mode="normal")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=updater, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        session = self.store.load("default")
        self.assertIn("session_id", session)
        self.assertIn("selected_mode", session)


class TestWriteAtomicUsesThreadUniqueNames(unittest.TestCase):
    """_write_atomic() must use thread-unique tmp names (not a shared .tmp suffix)."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.store = SessionStore(Path(self._td.name) / "sessions")

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_no_shared_tmp_file_suffix(self) -> None:
        """_write_atomic() must NOT use path.with_suffix('.tmp') fixed name."""
        src_path = Path(__file__).parent.parent / "src" / "session_store.py"
        src = src_path.read_text(encoding="utf-8")
        # Old fixed-suffix pattern must be gone
        self.assertNotIn('path.with_suffix(path.suffix + ".tmp")', src,
                         "_write_atomic must not use a fixed .tmp suffix")

    def test_uses_thread_unique_tmp_name(self) -> None:
        """_write_atomic() uses threading.get_ident() in the tmp filename."""
        src_path = Path(__file__).parent.parent / "src" / "session_store.py"
        src = src_path.read_text(encoding="utf-8")
        self.assertIn("threading.get_ident()", src,
                      "_write_atomic must use threading.get_ident() for unique tmp names")

    def test_write_atomic_leaves_no_tmp_file(self) -> None:
        """After _write_atomic(), no .tmp file is left behind."""
        target = Path(self._td.name) / "sessions" / "test.json"
        self.store._write_atomic(target, {"session_id": "test"})
        tmp_files = list(Path(self._td.name).rglob("*.tmp"))
        self.assertEqual(tmp_files, [], f"Orphaned tmp files: {tmp_files}")


class TestSourceContainsLock(unittest.TestCase):
    """Source-text assertions: lock usage must appear in session_store.py."""

    def setUp(self) -> None:
        src_path = Path(__file__).parent.parent / "src" / "session_store.py"
        self._src = src_path.read_text(encoding="utf-8")

    def test_imports_threading(self) -> None:
        self.assertIn("import threading", self._src)

    def test_lock_in_init(self) -> None:
        self.assertIn("threading.Lock()", self._src)

    def test_lock_used_in_append_message(self) -> None:
        start = self._src.index("def append_message(")
        end = self._src.index("\n    def ", start + 1)
        body = self._src[start:end]
        self.assertIn("self._lock", body)

    def test_lock_used_in_update(self) -> None:
        start = self._src.index("def update(")
        end = self._src.index("\n    def ", start + 1)
        body = self._src[start:end]
        self.assertIn("self._lock", body)


if __name__ == "__main__":
    unittest.main()
