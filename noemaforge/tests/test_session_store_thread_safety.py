#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_session_store_thread_safety.py
Zone: tests
Version: 0.32.2
Created: 2026-05-31
Modified: 2026-05-31
Purpose: Verify task-56/57/58 fixes:
  56 — events_api() response shape must include server_epoch and rotation_count
       so test stubs cannot silently hide regressions on these fields.
  57 — app.js pollEvents() must not adopt an empty server_epoch from error paths
       (empty string is falsy and would leave lastServerEpoch=null, making the
       restart-detection comparison always false).
  58 — SessionStore must be thread-safe: RLock serialises all write paths so
       concurrent append_message() calls do not interleave JSONL rows.
Inputs: SessionStore from session_store; source text of admin_gui_server.py and app.js.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_session_store_thread_safety.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path


def _install_stubs() -> None:
    stub_ver = types.ModuleType("noemaforge_version")
    stub_ver.RUNTIME_VERSION = "0.32.2"
    sys.modules.setdefault("noemaforge_version", stub_ver)

    stub_orch = types.ModuleType("orchestration_state")
    stub_orch.nowz = lambda: "2026-05-31T00:00:00Z"

    def _norm(r):
        r.setdefault("session_id", "default")
        r.setdefault("messages", [])
        r.setdefault("selected_mode", "normal")
        r.setdefault("selected_composite_top_n", 0)
        r.setdefault("active_jobs", [])
        return r

    stub_orch.normalize_session_record = _norm
    sys.modules.setdefault("orchestration_state", stub_orch)


_install_stubs()

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from session_store import SessionStore  # noqa: E402


# ===========================================================================
# Section 1 — task-56: events_api() response shape includes server_epoch
# ===========================================================================

class TestEventsApiResponseShape(unittest.TestCase):
    """events_api() source must include server_epoch and rotation_count fields."""

    def _get_events_api_body(self) -> str:
        source = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")
        start = source.index("def events_api(self")
        try:
            end = source.index("\n    def ", start + 1)
        except ValueError:
            end = len(source)
        return source[start:end]

    def test_server_epoch_in_ok_return(self):
        """events_api() ok=True return must include server_epoch."""
        body = self._get_events_api_body()
        self.assertIn('"server_epoch"', body,
                      "events_api() ok-path must return server_epoch field")

    def test_rotation_count_in_ok_return(self):
        """events_api() ok=True return must include rotation_count."""
        body = self._get_events_api_body()
        self.assertIn('"rotation_count"', body,
                      "events_api() ok-path must return rotation_count field")

    def test_server_epoch_in_error_return(self):
        """events_api() error path must also include server_epoch (even if empty)."""
        body = self._get_events_api_body()
        # Count occurrences of server_epoch — should appear in both ok and error paths
        import re
        count = len(re.findall(r'"server_epoch"', body))
        self.assertGreaterEqual(count, 2,
                                "server_epoch must appear in both ok and error return paths "
                                "so callers can always trust the field exists")

    def test_rotation_count_in_error_return(self):
        """events_api() error path must also include rotation_count."""
        body = self._get_events_api_body()
        import re
        count = len(re.findall(r'"rotation_count"', body))
        self.assertGreaterEqual(count, 2,
                                "rotation_count must appear in both ok and error return paths")


# ===========================================================================
# Section 2 — task-57: empty server_epoch not adopted in pollEvents()
# ===========================================================================

class TestPollEventsEmptyEpoch(unittest.TestCase):
    """app.js must not store empty string as server_epoch on first poll."""

    def _get_app_js(self) -> str:
        return (_SRC.parent / "templates" / "pipeline-dashboard" / "app.js").read_text(
            encoding="utf-8"
        )

    def test_truthy_check_before_epoch_assignment(self):
        """First-poll epoch assignment must guard against falsy values."""
        src = self._get_app_js()
        # Find the first-poll assignment line
        # It must be conditional on r.server_epoch being truthy, not just null check.
        # The old (broken) form: if(lastServerEpoch === null) lastServerEpoch = r.server_epoch || null;
        # The fixed form must check r.server_epoch truthy before assigning.
        self.assertNotIn(
            "lastServerEpoch = r.server_epoch || null",
            src,
            "First-poll epoch assignment must not use || null fallback; "
            "use a truthy guard to reject empty strings from error paths"
        )

    def test_nonempty_epoch_check_present(self):
        """Source must check r.server_epoch truthy before assigning lastServerEpoch."""
        src = self._get_app_js()
        # The fix: if(lastServerEpoch === null && r.server_epoch) lastServerEpoch = r.server_epoch;
        self.assertTrue(
            ("&& r.server_epoch" in src or "if(r.server_epoch)" in src
             or "r.server_epoch &&" in src),
            "pollEvents() must guard against empty server_epoch before assigning lastServerEpoch"
        )

    def test_epoch_comparison_guards_truthy(self):
        """Epoch-change comparison already guards with r.server_epoch truthy check."""
        src = self._get_app_js()
        # The comparison: if(r.server_epoch && r.server_epoch !== lastServerEpoch)
        self.assertIn("r.server_epoch &&", src,
                      "Epoch change comparison must verify r.server_epoch is truthy first")


# ===========================================================================
# Section 3 — task-58: SessionStore thread safety
# ===========================================================================

class TestSessionStoreLock(unittest.TestCase):
    """SessionStore must have a reentrant lock for thread-safe write operations."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.store = SessionStore(root=Path(self._tmpdir))

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_has_lock_attribute(self):
        """SessionStore must have a _lock attribute."""
        self.assertTrue(hasattr(self.store, "_lock"),
                        "SessionStore must have self._lock for thread safety")

    def test_lock_is_rlock(self):
        """The lock must be reentrant (RLock) to allow update()→load()→save() chains."""
        # RLock can be acquired multiple times by the same thread
        self.store._lock.acquire()
        acquired = self.store._lock.acquire(blocking=False)
        self.assertTrue(acquired, "self._lock must be an RLock (reentrant)")
        self.store._lock.release()
        self.store._lock.release()

    def test_source_has_rlock(self):
        """session_store.py must use threading.RLock() not threading.Lock()."""
        source = (_SRC / "session_store.py").read_text(encoding="utf-8")
        self.assertIn("RLock", source,
                      "SessionStore must use threading.RLock() for reentrant locking")

    def test_concurrent_append_message_no_corruption(self):
        """Concurrent append_message() calls must not corrupt the JSONL event log."""
        n_threads = 8
        n_messages = 10
        errors = []

        def writer(thread_id: int) -> None:
            try:
                for i in range(n_messages):
                    self.store.append_message(
                        "default",
                        {"role": "user", "content": f"thread={thread_id} msg={i}"},
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Thread errors: {errors}")

        # Verify session-events.jsonl is valid JSONL (no interleaved writes)
        if self.store.events_path.exists():
            for lineno, line in enumerate(
                self.store.events_path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if not line.strip():
                    continue
                try:
                    json.loads(line)
                except json.JSONDecodeError as exc:
                    self.fail(f"JSONL corruption on line {lineno}: {exc!r}\nLine: {line!r}")

        # Verify session JSON contains all messages (not just valid JSONL).
        # Without proper locking, a late thread's save() could overwrite an
        # earlier thread's save(), silently dropping messages from the session.
        final_session = self.store.load("default")
        final_messages = final_session.get("messages", [])
        self.assertEqual(
            len(final_messages), n_threads * n_messages,
            f"Expected {n_threads * n_messages} messages in session JSON after concurrent "
            f"append_message() calls; got {len(final_messages)}. "
            "This indicates a lost-update race despite RLock."
        )

    def test_load_and_save_do_not_deadlock(self):
        """load() followed by save() must not deadlock (RLock allows re-entry)."""
        session = self.store.load("default")
        self.assertIsNotNone(session)
        session["custom_field"] = "test"
        saved = self.store.save(session)
        self.assertEqual(saved.get("custom_field"), "test")

    def test_update_does_not_deadlock(self):
        """update() calls load() and save() internally; must not deadlock."""
        result = self.store.update("default", test_key="hello")
        self.assertEqual(result.get("test_key"), "hello")


if __name__ == "__main__":
    unittest.main()
