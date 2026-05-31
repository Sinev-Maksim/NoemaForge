#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_job_get_cancel_normalize.py
Zone: tests
Version: 0.32.2
Created: 2026-06-01
Modified: 2026-06-01
Purpose: Tests for tasks 81-85:
           - task-81 (MEDIUM): save_message() must call session_store.append_message()
             exactly once per message (remove duplicate slim-dict call).
           - task-82/85 (MEDIUM): job_get() must acquire _jobs_lock and apply
             normalize_job_record() so the GET /api/jobs/{id} response matches
             the schema returned by GET /api/jobs (jobs_list).
           - task-83 (MEDIUM): job_cancel() return paths must include normalized
             job dicts (normalize_job_record + enrich_artifact_cards) so all
             schema fields are present and consistent with jobs_list().
           - task-84 (LOW): job_cancel() must only call _write_json(jobs_file)
             when a job was actually mutated (target is not None), avoiding a
             no-op disk write under lock for not-found requests.
Inputs: admin_gui_server.py source text; AdminGuiServer stub for behavioural tests.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_job_get_cancel_normalize.py -v
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


# ---------------------------------------------------------------------------
# Source-guard helpers
# ---------------------------------------------------------------------------

def _save_message_body() -> str:
    start = _ADMIN_SRC.index("def save_message(self")
    end = _ADMIN_SRC.index("\n    def ", start + 1)
    return _ADMIN_SRC[start:end]


def _job_get_body() -> str:
    start = _ADMIN_SRC.index("def job_get(self")
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
# task-81: save_message() must call append_message() exactly once
# ---------------------------------------------------------------------------

class TestSaveMessageNoDoubleAppend(unittest.TestCase):
    """task-81: save_message() must call session_store.append_message() exactly once."""

    def test_append_message_called_exactly_once(self) -> None:
        """append_message must appear exactly once in save_message() body."""
        body = _save_message_body()
        count = body.count("append_message(")
        self.assertEqual(count, 1,
                         f"save_message() must call append_message() exactly once (found {count})")

    def test_slim_dict_call_removed(self) -> None:
        """The slim-dict call {'role': role, 'text': text, ...} must be absent."""
        body = _save_message_body()
        # The removed call used a literal dict with 'role' and 'text' keys inline
        self.assertNotIn('"role": role, "persona": persona, "text": text', body,
                         "The slim-dict append_message call must be removed")

    def test_full_msg_call_present(self) -> None:
        """The full msg dict append_message call must be present."""
        body = _save_message_body()
        self.assertIn("append_message(", body,
                      "append_message() must still be called with the full msg dict")


# ---------------------------------------------------------------------------
# task-82/85: job_get() must hold _jobs_lock and call normalize_job_record
# ---------------------------------------------------------------------------

class TestJobGetLockNormalize(unittest.TestCase):
    """task-82/85: job_get() must acquire _jobs_lock and call normalize_job_record()."""

    def test_job_get_uses_jobs_lock(self) -> None:
        """job_get() must acquire self._jobs_lock."""
        self.assertIn("_jobs_lock", _job_get_body(),
                      "job_get() must acquire self._jobs_lock")

    def test_job_get_uses_with_statement(self) -> None:
        """job_get() must use 'with self._jobs_lock:' context manager."""
        body = _job_get_body()
        self.assertIn("with self._jobs_lock:", body,
                      "job_get() must use 'with self._jobs_lock:' context manager")

    def test_job_get_calls_normalize_job_record(self) -> None:
        """job_get() must call normalize_job_record() on the fetched job."""
        body = _job_get_body()
        self.assertIn("normalize_job_record", body,
                      "job_get() must call normalize_job_record()")

    def test_job_get_normalize_before_enrich(self) -> None:
        """normalize_job_record() must appear before enrich_artifact_cards() in job_get()."""
        body = _job_get_body()
        norm_idx = body.index("normalize_job_record")
        enrich_idx = body.index("enrich_artifact_cards", norm_idx)
        self.assertLess(norm_idx, enrich_idx,
                        "normalize_job_record() must precede enrich_artifact_cards() in job_get()")


class TestJobGetBehavioural(unittest.TestCase):
    """Behavioural: job_get() must return schema-complete job dicts."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_server(self):
        from admin_gui_server import AdminGuiServer, now_iso
        srv = object.__new__(AdminGuiServer)
        tmp = Path(self._tmpdir)
        srv.gui_state_dir = tmp / "gui"
        srv.gui_state_dir.mkdir(parents=True, exist_ok=True)
        srv.jobs_dir = tmp / "jobs"
        srv.jobs_dir.mkdir(parents=True, exist_ok=True)
        srv.session_store = types.SimpleNamespace(attach_active_jobs=lambda *a, **kw: None)
        srv._jobs_lock = threading.Lock()
        jobs_data = {"jobs": [
            {"job_id": "job_minimal", "status": "running", "kind": "test"},
        ]}
        (srv.jobs_dir / "jobs.json").write_text(json.dumps(jobs_data), encoding="utf-8")
        return srv

    def test_job_get_returns_all_schema_fields(self) -> None:
        """job_get() must return a schema-complete job dict."""
        from admin_gui_server import AdminGuiServer
        srv = self._make_server()
        result = AdminGuiServer.job_get(srv, "job_minimal")
        self.assertTrue(result["ok"])
        for field in ("job_id", "kind", "status", "lock_key", "progress",
                      "artifacts", "created_at", "updated_at", "finished_at", "version"):
            with self.subTest(field=field):
                self.assertIn(field, result["job"],
                              f"job_get() response must include '{field}'")

    def test_job_get_not_found_returns_ok_false(self) -> None:
        """job_get() for non-existent job_id must return ok=False."""
        from admin_gui_server import AdminGuiServer
        srv = self._make_server()
        result = AdminGuiServer.job_get(srv, "nonexistent_job")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "job not found")


# ---------------------------------------------------------------------------
# task-83: job_cancel() must return normalized job dicts
# ---------------------------------------------------------------------------

class TestJobCancelNormalize(unittest.TestCase):
    """task-83: job_cancel() return paths must include normalize_job_record() output."""

    def test_job_cancel_calls_normalize_job_record(self) -> None:
        """normalize_job_record must be called inside job_cancel() body."""
        body = _job_cancel_body()
        self.assertIn("normalize_job_record", body,
                      "job_cancel() must call normalize_job_record() in return paths")

    def test_job_cancel_normalizes_final_state_return(self) -> None:
        """The FINAL_JOB_STATES early return must use a normalized dict."""
        body = _job_cancel_body()
        # normalize_job_record must appear before the first 'return' for FINAL states
        final_idx = body.index("FINAL_JOB_STATES")
        norm_idx = body.index("normalize_job_record", final_idx)
        return_idx = body.index("return", norm_idx)
        self.assertLess(norm_idx, return_idx,
                        "normalize_job_record() must precede the FINAL-state return")


class TestJobCancelNormalizeBehavioural(unittest.TestCase):
    """Behavioural: job_cancel() must include all schema fields in ok and error returns."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_server(self):
        from admin_gui_server import AdminGuiServer, now_iso
        srv = object.__new__(AdminGuiServer)
        tmp = Path(self._tmpdir)
        srv.gui_state_dir = tmp / "gui"
        srv.gui_state_dir.mkdir(parents=True, exist_ok=True)
        srv.jobs_dir = tmp / "jobs"
        srv.jobs_dir.mkdir(parents=True, exist_ok=True)
        srv.session_store = types.SimpleNamespace(attach_active_jobs=lambda *a, **kw: None)
        srv._jobs_lock = threading.Lock()
        jobs_data = {"jobs": [
            {"job_id": "job_done", "status": "done", "kind": "test"},
            {"job_id": "job_running", "status": "running", "kind": "test"},
        ]}
        (srv.jobs_dir / "jobs.json").write_text(json.dumps(jobs_data), encoding="utf-8")
        return srv

    def test_cancel_final_state_job_returns_normalized_dict(self) -> None:
        """Cancelling a done job must return a normalized job dict with all schema fields."""
        from admin_gui_server import AdminGuiServer
        srv = self._make_server()
        result = AdminGuiServer.job_cancel(srv, "job_done")
        self.assertFalse(result["ok"])
        for field in ("job_id", "kind", "status", "lock_key", "progress",
                      "artifacts", "created_at", "updated_at", "finished_at", "version"):
            with self.subTest(field=field):
                self.assertIn(field, result["job"],
                              f"Normalized job dict must include '{field}'")

    def test_cancel_running_job_returns_normalized_dict(self) -> None:
        """Cancelling a running job must return a normalized job dict with all schema fields."""
        from admin_gui_server import AdminGuiServer
        srv = self._make_server()
        result = AdminGuiServer.job_cancel(srv, "job_running")
        self.assertTrue(result["ok"])
        for field in ("job_id", "kind", "status", "lock_key", "progress",
                      "artifacts", "created_at", "updated_at", "finished_at", "version"):
            with self.subTest(field=field):
                self.assertIn(field, result["job"],
                              f"Normalized job dict must include '{field}'")


# ---------------------------------------------------------------------------
# task-84: job_cancel() must skip _write_json when no job was mutated
# ---------------------------------------------------------------------------

class TestJobCancelConditionalWrite(unittest.TestCase):
    """task-84: job_cancel() must not write jobs.json when the job is not found."""

    def test_conditional_write_guard_present(self) -> None:
        """'if target is not None:' guard must appear before _write_json(jobs_file) call."""
        body = _job_cancel_body()
        self.assertIn("if target is not None:", body,
                      "job_cancel() must guard _write_json with 'if target is not None:'")

    def test_write_json_inside_conditional(self) -> None:
        """_write_json(self.jobs_file(), data) must appear after the conditional guard."""
        body = _job_cancel_body()
        guard_idx = body.index("if target is not None:")
        write_idx = body.index("self._write_json(self.jobs_file(), data)", guard_idx)
        self.assertLess(guard_idx, write_idx,
                        "_write_json(jobs_file) must be guarded by 'if target is not None:'")

    def test_not_found_does_not_write_jobs_json(self) -> None:
        """Cancelling a non-existent job must not modify jobs.json."""
        import time
        from admin_gui_server import AdminGuiServer
        tmpdir = tempfile.mkdtemp()
        try:
            tmp = Path(tmpdir)
            srv = object.__new__(AdminGuiServer)
            srv.gui_state_dir = tmp / "gui"
            srv.gui_state_dir.mkdir(parents=True, exist_ok=True)
            srv.jobs_dir = tmp / "jobs"
            srv.jobs_dir.mkdir(parents=True, exist_ok=True)
            srv._jobs_lock = threading.Lock()
            srv.session_store = types.SimpleNamespace(attach_active_jobs=lambda *a, **kw: None)
            jobs_data = {"jobs": [{"job_id": "job1", "status": "running", "kind": "test"}]}
            jobs_file = srv.jobs_dir / "jobs.json"
            jobs_file.write_text(json.dumps(jobs_data), encoding="utf-8")
            mtime_before = jobs_file.stat().st_mtime
            time.sleep(0.05)  # ensure mtime resolution
            result = AdminGuiServer.job_cancel(srv, "nonexistent_id")
            mtime_after = jobs_file.stat().st_mtime
            self.assertFalse(result["ok"])
            self.assertAlmostEqual(mtime_before, mtime_after, delta=0.01,
                                   msg="jobs.json must not be modified for not-found cancel")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
