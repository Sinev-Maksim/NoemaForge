#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_conv_lock_tasks_list_lock.py
Zone: tests
Version: 0.32.2
Created: 2026-06-01
Modified: 2026-06-01
Purpose: Tests for tasks 94-95:
           - task-94 (MEDIUM): tasks_list() must acquire self._tasks_lock before
             calling tasks_data() so GET /api/tasks reads are consistent with
             concurrent task_create()/task_update() writes.
           - task-95 (MEDIUM): save_message() must acquire self._conv_lock around
             the _conversation() + _save_conversation() R-M-W cycle to prevent
             concurrent request threads from racing on conversation-current.json.
             Lock order: _tasks_lock → _conv_lock (task_create holds _tasks_lock
             then calls save_message — never reversed).
Inputs: admin_gui_server.py source text.
Outputs: pytest pass/fail.
Side effects: None.
Tests: python3 -m unittest noemaforge/tests/test_conv_lock_tasks_list_lock.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _install_stubs() -> None:
    import noemaforge_version as real_version
    sys.modules.setdefault("noemaforge_version", real_version)

    stub_orch = types.ModuleType("orchestration_state")
    stub_orch.nowz = lambda: "2026-06-01T00:00:00Z"
    stub_orch.normalize_session_record = lambda r: r
    stub_orch.normalize_job_record = lambda r: r
    stub_orch.is_active_job = lambda job: False
    stub_orch.ACTIVE_JOB_STATES = {"queued", "starting", "running", "cancel_requested", "needs_privilege"}
    stub_orch.FINAL_JOB_STATES = {"done", "failed", "cancelled"}
    sys.modules.setdefault("orchestration_state", stub_orch)

    stub_prod = types.ModuleType("production_ai_contracts")
    stub_prod.new_trace_id = lambda kind="": f"trace_{kind}"
    sys.modules.setdefault("production_ai_contracts", stub_prod)

    stub_priv = types.ModuleType("privileged_gui_job_runner")
    stub_priv.enrich_privileged_job = lambda job, **_kw: job
    sys.modules.setdefault("privileged_gui_job_runner", stub_priv)


_install_stubs()

_ADMIN_SRC = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")


def _tasks_list_body() -> str:
    start = _ADMIN_SRC.index("def tasks_list(self)")
    end = _ADMIN_SRC.index("\n    def ", start + 1)
    return _ADMIN_SRC[start:end]


def _save_message_body() -> str:
    start = _ADMIN_SRC.index("def save_message(self")
    end = _ADMIN_SRC.index("\n    def ", start + 1)
    return _ADMIN_SRC[start:end]


def _init_body() -> str:
    start = _ADMIN_SRC.index("def __init__(self, address:")
    end = _ADMIN_SRC.index("\n    def ", start + 1)
    return _ADMIN_SRC[start:end]


# ---------------------------------------------------------------------------
# task-94: tasks_list() must use _tasks_lock
# ---------------------------------------------------------------------------

class TestTasksListLock(unittest.TestCase):
    """task-94: tasks_list() must acquire self._tasks_lock for consistent reads."""

    def test_tasks_list_uses_tasks_lock(self) -> None:
        """tasks_list() body must reference _tasks_lock."""
        self.assertIn("_tasks_lock", _tasks_list_body(),
                      "tasks_list() must acquire self._tasks_lock")

    def test_tasks_list_uses_with_statement(self) -> None:
        """tasks_list() must use 'with self._tasks_lock:' context manager."""
        body = _tasks_list_body()
        self.assertIn("with self._tasks_lock:", body,
                      "tasks_list() must use 'with self._tasks_lock:' context manager")

    def test_tasks_data_inside_lock(self) -> None:
        """tasks_data() must be called after 'with self._tasks_lock:' in tasks_list()."""
        body = _tasks_list_body()
        lock_idx = body.index("with self._tasks_lock:")
        data_idx = body.index("tasks_data()", lock_idx)
        self.assertLess(lock_idx, data_idx,
                        "tasks_data() must be called inside the _tasks_lock block")


# ---------------------------------------------------------------------------
# task-95: save_message() must use _conv_lock
# ---------------------------------------------------------------------------

class TestConvLock(unittest.TestCase):
    """task-95: save_message() must acquire self._conv_lock around conversation R-M-W."""

    def test_conv_lock_declared_in_init(self) -> None:
        """AdminGuiServer.__init__ must declare self._conv_lock."""
        self.assertIn("_conv_lock", _init_body(),
                      "AdminGuiServer must declare self._conv_lock in __init__")

    def test_conv_lock_is_threading_lock(self) -> None:
        """_conv_lock must be created as threading.Lock()."""
        init_body = _init_body()
        self.assertIn("_conv_lock = threading.Lock()", init_body,
                      "_conv_lock must be created as threading.Lock()")

    def test_save_message_uses_conv_lock(self) -> None:
        """save_message() must acquire self._conv_lock."""
        self.assertIn("_conv_lock", _save_message_body(),
                      "save_message() must acquire self._conv_lock")

    def test_save_message_uses_with_statement(self) -> None:
        """save_message() must use 'with self._conv_lock:' context manager."""
        body = _save_message_body()
        self.assertIn("with self._conv_lock:", body,
                      "save_message() must use 'with self._conv_lock:' context manager")

    def test_conversation_read_inside_lock(self) -> None:
        """_conversation() call must appear after 'with self._conv_lock:' in save_message()."""
        body = _save_message_body()
        lock_idx = body.index("with self._conv_lock:")
        conv_idx = body.index("self._conversation()", lock_idx)
        self.assertLess(lock_idx, conv_idx,
                        "_conversation() must be called inside the _conv_lock block")

    def test_save_conversation_inside_lock(self) -> None:
        """_save_conversation() call must appear inside the _conv_lock block."""
        body = _save_message_body()
        lock_idx = body.index("with self._conv_lock:")
        save_idx = body.index("self._save_conversation(", lock_idx)
        self.assertLess(lock_idx, save_idx,
                        "_save_conversation() must be called inside the _conv_lock block")

    def test_lock_order_comment_present(self) -> None:
        """A comment must document the lock order (_tasks_lock -> _conv_lock)."""
        body = _save_message_body()
        self.assertIn("_tasks_lock", body,
                      "save_message() must document lock order _tasks_lock → _conv_lock")

    def test_conversation_before_save_inside_lock(self) -> None:
        """_conversation() must appear before _save_conversation() inside the lock."""
        body = _save_message_body()
        lock_idx = body.index("with self._conv_lock:")
        conv_idx = body.index("self._conversation()", lock_idx)
        save_idx = body.index("self._save_conversation(", conv_idx)
        self.assertLess(conv_idx, save_idx,
                        "_conversation() must precede _save_conversation() inside lock")


if __name__ == "__main__":
    unittest.main()
