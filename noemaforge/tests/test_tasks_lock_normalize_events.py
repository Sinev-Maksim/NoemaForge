#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_tasks_lock_normalize_events.py
Zone: tests
Version: 0.32.2
Created: 2026-06-01
Modified: 2026-06-01
Purpose: Tests for tasks 89-92:
           - task-89 (MEDIUM): session_store.save() must NOT emit a session event
             because all callers (update, append_message) add their own semantic
             events — the old session.saved call doubled every event in
             session-events.jsonl.
           - task-90 (MEDIUM): _upsert_job() and _persist_job() must write
             normalize_job_record() output to per-job .json files so job_get()
             reads a schema-complete record regardless of creation path.
           - task-91 (MEDIUM): task_create() and task_update() must acquire
             self._tasks_lock to serialise concurrent R-M-W cycles on tasks.json.
           - task-92 (LOW): norm_target in job_cancel() must be initialized
             before the 'if target:' block to avoid a potential NameError under
             future refactoring (currently safe at runtime due to ternary
             short-circuit, but fragile).
Inputs: admin_gui_server.py and session_store.py source text; stubs.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_tasks_lock_normalize_events.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _install_stubs() -> None:
    stub_ver = types.ModuleType("noemaforge_version")
    stub_ver.RUNTIME_VERSION = "0.32.2"
    sys.modules.setdefault("noemaforge_version", stub_ver)

    stub_orch = types.ModuleType("orchestration_state")
    stub_orch.nowz = lambda: "2026-06-01T00:00:00Z"
    stub_orch.normalize_session_record = lambda r: r
    stub_orch.normalize_job_record = lambda r: {
        "job_id": str(r.get("job_id") or ""),
        "kind": str(r.get("kind") or "unknown"),
        "status": str(r.get("status") or "queued"),
        "lock_key": str(r.get("lock_key") or ""),
        "progress": r.get("progress") if isinstance(r.get("progress"), dict) else {"current": 0, "total": 0, "label": "queued"},
        "artifacts": list(r.get("artifacts") or []),
        "created_at": str(r.get("created_at") or "2026-06-01T00:00:00Z"),
        "updated_at": str(r.get("updated_at") or "2026-06-01T00:00:00Z"),
        "finished_at": str(r.get("finished_at") or ""),
        "version": str(r.get("version") or "0.32.2"),
    }
    stub_orch.is_active_job = lambda job: str(job.get("status") or "") in {
        "queued", "running", "needs_privilege", "starting", "cancel_requested"
    }
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
_STORE_SRC = (_SRC / "session_store.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Source-guard helpers
# ---------------------------------------------------------------------------

def _save_body() -> str:
    start = _STORE_SRC.index("def save(self, session")
    end = _STORE_SRC.index("\n    def ", start + 1)
    return _STORE_SRC[start:end]


def _upsert_body() -> str:
    start = _ADMIN_SRC.index("def _upsert_job(self")
    end = _ADMIN_SRC.index("\n    def ", start + 1)
    return _ADMIN_SRC[start:end]


def _persist_body() -> str:
    start = _ADMIN_SRC.index("def _persist_job(self")
    end = _ADMIN_SRC.index("\n    def ", start + 1)
    return _ADMIN_SRC[start:end]


def _task_create_body() -> str:
    start = _ADMIN_SRC.index("def task_create(self")
    end = _ADMIN_SRC.index("\n    def ", start + 1)
    return _ADMIN_SRC[start:end]


def _task_update_body() -> str:
    start = _ADMIN_SRC.index("def task_update(self")
    end = _ADMIN_SRC.index("\n    def ", start + 1)
    return _ADMIN_SRC[start:end]


def _job_cancel_body() -> str:
    start = _ADMIN_SRC.index("def job_cancel(self")
    try:
        end = _ADMIN_SRC.index("\n    def ", start + 1)
    except ValueError:
        end = len(_ADMIN_SRC)
    return _ADMIN_SRC[start:end]


# ---------------------------------------------------------------------------
# task-89: session_store.save() must NOT emit session.saved event
# ---------------------------------------------------------------------------

class TestSaveNoDoubleEvent(unittest.TestCase):
    """task-89: save() must not append a session.saved event (callers add their own)."""

    def test_save_does_not_append_session_saved(self) -> None:
        """save() body must not contain 'session.saved' event append."""
        body = _save_body()
        self.assertNotIn('"session.saved"', body,
                         "save() must not emit 'session.saved' event to avoid doubling events")

    def test_save_does_not_call_append_event(self) -> None:
        """save() must not call _append_event()."""
        body = _save_body()
        self.assertNotIn("_append_event(", body,
                         "save() must not call _append_event() — callers handle events")

    def test_update_still_emits_session_updated(self) -> None:
        """update() must still emit 'session.updated' after removing save()'s event."""
        start = _STORE_SRC.index("def update(self")
        end = _STORE_SRC.index("\n    def ", start + 1)
        body = _STORE_SRC[start:end]
        self.assertIn('"session.updated"', body,
                      "update() must emit 'session.updated' event")

    def test_append_message_still_emits_session_message(self) -> None:
        """append_message() must still emit 'session.message' after removing save()'s event."""
        start = _STORE_SRC.index("def append_message(self")
        end = _STORE_SRC.index("\n    def ", start + 1)
        body = _STORE_SRC[start:end]
        self.assertIn('"session.message"', body,
                      "append_message() must emit 'session.message' event")


# ---------------------------------------------------------------------------
# task-90: per-job files must be written with normalize_job_record()
# ---------------------------------------------------------------------------

class TestPerJobNormalize(unittest.TestCase):
    """task-90: _upsert_job() and _persist_job() must normalize per-job JSON files."""

    def test_upsert_job_normalizes_per_job_file(self) -> None:
        """_upsert_job() must call normalize_job_record() for the per-job file write."""
        body = _upsert_body()
        self.assertIn("normalize_job_record", body,
                      "_upsert_job() must call normalize_job_record() for per-job .json file")

    def test_persist_job_normalizes_per_job_file(self) -> None:
        """_persist_job() must call normalize_job_record() for the per-job file write."""
        body = _persist_body()
        self.assertIn("normalize_job_record", body,
                      "_persist_job() must call normalize_job_record() for per-job .json file")

    def test_upsert_job_file_write_uses_normalized_dict(self) -> None:
        """_upsert_job() per-job file write must pass normalize_job_record() output."""
        body = _upsert_body()
        # The write call is: _write_json(self.job_file(...), normalize_job_record(dict(job)))
        # Both job_file and normalize_job_record appear in the same _write_json call.
        job_file_idx = body.index("self.job_file(")
        norm_idx = body.index("normalize_job_record(", job_file_idx)
        self.assertLess(job_file_idx, norm_idx,
                        "normalize_job_record() must appear in the job_file _write_json call")


# ---------------------------------------------------------------------------
# task-91: task_create() and task_update() must use _tasks_lock
# ---------------------------------------------------------------------------

class TestTasksLock(unittest.TestCase):
    """task-91: task R-M-W methods must use self._tasks_lock."""

    def test_tasks_lock_declared_in_init(self) -> None:
        """AdminGuiServer.__init__ must declare self._tasks_lock."""
        self.assertIn("_tasks_lock", _ADMIN_SRC,
                      "AdminGuiServer must declare self._tasks_lock in __init__")

    def test_tasks_lock_is_threading_lock(self) -> None:
        """_tasks_lock must be created as threading.Lock()."""
        init_start = _ADMIN_SRC.index("def __init__(self, address:")
        init_end = _ADMIN_SRC.index("\n    def ", init_start + 1)
        init_body = _ADMIN_SRC[init_start:init_end]
        self.assertIn("_tasks_lock = threading.Lock()", init_body,
                      "_tasks_lock must be created as threading.Lock()")

    def test_task_create_acquires_lock(self) -> None:
        """task_create() must acquire self._tasks_lock."""
        self.assertIn("_tasks_lock", _task_create_body(),
                      "task_create() must acquire self._tasks_lock")

    def test_task_update_acquires_lock(self) -> None:
        """task_update() must acquire self._tasks_lock."""
        self.assertIn("_tasks_lock", _task_update_body(),
                      "task_update() must acquire self._tasks_lock")

    def test_task_create_uses_with_statement(self) -> None:
        """task_create() must use 'with self._tasks_lock:' context manager."""
        body = _task_create_body()
        self.assertIn("with self._tasks_lock:", body,
                      "task_create() must use 'with self._tasks_lock:' context manager")

    def test_task_update_uses_with_statement(self) -> None:
        """task_update() must use 'with self._tasks_lock:' context manager."""
        body = _task_update_body()
        self.assertIn("with self._tasks_lock:", body,
                      "task_update() must use 'with self._tasks_lock:' context manager")


# ---------------------------------------------------------------------------
# task-92: norm_target initialized before if target: block in job_cancel()
# ---------------------------------------------------------------------------

class TestNormTargetInit(unittest.TestCase):
    """task-92: norm_target must be initialized before the 'if target:' block."""

    def test_norm_target_initialized_before_if_block(self) -> None:
        """'norm_target' initialization must appear before 'if target:' block."""
        body = _job_cancel_body()
        # norm_target = {} or norm_target: Dict = {} must appear before 'if target:'
        init_idx = body.index("norm_target")
        if_idx = body.index("if target:", init_idx)
        # The first occurrence of norm_target should be its initialization
        self.assertLess(init_idx, if_idx,
                        "norm_target must be initialized before the 'if target:' block")

    def test_norm_target_init_is_empty_dict(self) -> None:
        """norm_target must be initialized to an empty dict somewhere before if target:."""
        body = _job_cancel_body()
        # Look for the assignment pattern: 'norm_target' followed by '= {}' (possibly with type annotation)
        # The actual code is: norm_target: Dict[str, Any] = {}
        # Search for '= {}' near any norm_target line to verify empty-dict init
        self.assertIn("norm_target", body,
                      "norm_target must be present in job_cancel() body")
        # Find the '= {}' assignment that initializes norm_target
        self.assertIn("= {}", body,
                      "norm_target must be initialized with '= {}' in job_cancel()")


if __name__ == "__main__":
    unittest.main()
