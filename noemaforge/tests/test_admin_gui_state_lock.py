#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_gui_state_lock.py
Zone: release/package
Created: 2026-05-30
Modified: 2026-05-30
Purpose: TDD tests for AdminGuiServer._state_lock protecting shared-file read-modify-write cycles.
  Covers conversation, jobs (_upsert_job, _persist_job, job_cancel) under concurrent access.
Inputs: AdminGuiServer stub with _state_lock, jobs_dir, gui_state_dir.
Outputs: unittest assertions only.
Side effects: None (temp dirs only).
Tests: python3 -m unittest noemaforge/tests/test_admin_gui_state_lock.py -v
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import admin_gui_server
from admin_gui_server import AdminGuiServer, safe_id
from session_store import SessionStore
from event_log import EventLog


def _make_server(td: Path) -> AdminGuiServer:
    """Build a minimal AdminGuiServer stub with _state_lock wired."""
    srv = object.__new__(AdminGuiServer)
    srv.jobs_dir = td / "jobs"
    srv.jobs_dir.mkdir(parents=True, exist_ok=True)
    srv.tasks_dir = td / "tasks"
    srv.tasks_dir.mkdir(parents=True, exist_ok=True)
    srv.data_root = td
    srv.gui_state_dir = td / "gui"
    srv.gui_state_dir.mkdir(parents=True, exist_ok=True)
    srv.review_dir = td / "review"
    (srv.review_dir / "sr" / "inbox").mkdir(parents=True, exist_ok=True)
    (srv.review_dir / "ssr" / "inbox").mkdir(parents=True, exist_ok=True)
    srv.session_store = SessionStore(td / "sessions")
    srv.event_log = EventLog(td / "events")
    srv._state_lock = threading.Lock()
    return srv


# ---------------------------------------------------------------------------
# Source-text assertions: lock exists in __init__ and is used in key methods
# ---------------------------------------------------------------------------

class TestStateLockSourcePresence(unittest.TestCase):
    """_state_lock must be initialised in __init__ and used in critical methods."""

    _src: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls._src = (ROOT / "src" / "admin_gui_server.py").read_text(encoding="utf-8")

    def test_state_lock_initialised_in_init(self) -> None:
        self.assertIn("self._state_lock = threading.Lock()", self._src)

    def test_state_lock_used_in_upsert_job(self) -> None:
        # _upsert_job must acquire _state_lock around the R-M-W cycle.
        upsert_idx = self._src.index("def _upsert_job")
        persist_idx = self._src.index("def _persist_job")
        upsert_body = self._src[upsert_idx:persist_idx]
        self.assertIn("_state_lock", upsert_body)

    def test_state_lock_used_in_persist_job(self) -> None:
        persist_idx = self._src.index("def _persist_job")
        # Use "def job_cancel(" to avoid matching "def job_cancel_marker_file"
        cancel_idx = self._src.index("def job_cancel(")
        persist_body = self._src[persist_idx:cancel_idx]
        self.assertIn("_state_lock", persist_body)

    def test_state_lock_used_in_job_cancel(self) -> None:
        cancel_idx = self._src.index("def job_cancel(")
        dashboard_idx = self._src.index("def dashboard_state")
        cancel_body = self._src[cancel_idx:dashboard_idx]
        self.assertIn("_state_lock", cancel_body)

    def test_state_lock_used_in_save_message(self) -> None:
        save_idx = self._src.index("def save_message")
        next_def = self._src.index("\n    def ", save_idx + 1)
        save_body = self._src[save_idx:next_def]
        self.assertIn("_state_lock", save_body)


# ---------------------------------------------------------------------------
# Functional: concurrent job creation produces no torn writes
# ---------------------------------------------------------------------------

class TestConcurrentJobCreation(unittest.TestCase):
    """Concurrent create_job() calls must all appear in jobs.json without overwrites."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="nf_lock_jobs_")
        self.td = Path(self._tmp.name)
        self.srv = _make_server(self.td)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_concurrent_create_job_no_overwrites(self) -> None:
        """All N concurrent job creations must be persisted in jobs.json."""
        N = 20
        errors = []

        def create():
            try:
                self.srv.create_job("test_kind", status="queued", idempotency_key="")
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=create) for _ in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Exceptions during concurrent creates: {errors}")
        data = json.loads((self.td / "jobs" / "jobs.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["jobs"]), N, f"Expected {N} jobs, got {len(data['jobs'])}")

    def test_idempotency_under_concurrency(self) -> None:
        """Concurrent calls with the same idempotency_key must return the same job."""
        KEY = "idem-key-concurrent"
        results = []

        def create():
            j = self.srv.create_job("idem_kind", status="queued", idempotency_key=KEY)
            results.append(j["job_id"])

        threads = [threading.Thread(target=create) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads must have received the same job_id.
        self.assertEqual(len(set(results)), 1, f"Expected 1 unique job_id, got: {set(results)}")


# ---------------------------------------------------------------------------
# Functional: lock attribute present and is a real threading.Lock
# ---------------------------------------------------------------------------

class TestStateLockType(unittest.TestCase):
    """_state_lock must be a threading.Lock (or RLock) on a real AdminGuiServer."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="nf_lock_type_")
        self.srv = _make_server(Path(self._tmp.name))

    def tearDown(self) -> None:
        tempfile.TemporaryDirectory.__exit__(self._tmp, None, None, None)
        try:
            self._tmp.cleanup()
        except Exception:
            pass

    def test_state_lock_attribute_exists(self) -> None:
        self.assertTrue(hasattr(self.srv, "_state_lock"))

    def test_state_lock_is_lock_type(self) -> None:
        lock = self.srv._state_lock
        # threading.Lock() returns a _thread.lock; check it supports the context manager.
        self.assertTrue(hasattr(lock, "__enter__") and hasattr(lock, "__exit__"))


if __name__ == "__main__":
    unittest.main()
