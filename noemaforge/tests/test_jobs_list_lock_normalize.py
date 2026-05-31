#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_jobs_list_lock_normalize.py
Zone: tests
Version: 0.32.2
Created: 2026-06-01
Modified: 2026-06-01
Purpose: Tests for tasks 77-79:
           - task-77 (MEDIUM): jobs_list() must acquire self._jobs_lock before
             calling jobs_data() to make the read consistent with the write
             callers (_upsert_job, _persist_job, job_cancel).
           - task-78 (LOW): The per-job JSON and cancel-marker writes in
             job_cancel() are intentionally outside _jobs_lock; a comment
             must document this as idempotent/atomic and therefore safe.
           - task-79 (LOW): jobs_list() must call normalize_job_record() on
             each raw job dict before returning it, guaranteeing all schema
             fields are present with safe defaults.
         Tests are source-guard checks plus a focused behavioural test for
         task-79 (missing-field normalization).
Inputs: admin_gui_server.py source text; AdminGuiServer stub for behavioural tests.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_jobs_list_lock_normalize.py -v
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

def _jobs_list_body() -> str:
    start = _ADMIN_SRC.index("def jobs_list(self)")
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
# task-77: jobs_list() must acquire _jobs_lock
# ---------------------------------------------------------------------------

class TestJobsListLock(unittest.TestCase):
    """task-77: jobs_list() must acquire self._jobs_lock for consistent reads."""

    def test_jobs_list_uses_jobs_lock(self) -> None:
        """_jobs_lock must appear inside jobs_list() body."""
        self.assertIn("_jobs_lock", _jobs_list_body(),
                      "jobs_list() must acquire self._jobs_lock")

    def test_jobs_list_uses_with_statement(self) -> None:
        """jobs_list() must use a 'with self._jobs_lock:' context manager."""
        body = _jobs_list_body()
        self.assertIn("with self._jobs_lock:", body,
                      "jobs_list() must use 'with self._jobs_lock:' context manager")

    def test_jobs_data_called_inside_lock(self) -> None:
        """jobs_data() call must appear inside the lock block (after 'with self._jobs_lock:')."""
        body = _jobs_list_body()
        lock_idx = body.index("with self._jobs_lock:")
        data_idx = body.index("jobs_data()", lock_idx)
        self.assertLess(lock_idx, data_idx,
                        "jobs_data() must be called after 'with self._jobs_lock:'")

    def test_session_store_sync_outside_lock(self) -> None:
        """session_store.attach_active_jobs() call must appear after the lock block ends."""
        body = _jobs_list_body()
        # The lock block ends when indentation returns to method level.
        # 'attach_active_jobs' should appear after 'with self._jobs_lock:' block closes.
        lock_idx = body.index("with self._jobs_lock:")
        attach_idx = body.index("attach_active_jobs", lock_idx)
        # Find the 'return' of the lock block — the next statement at method indent.
        # A reliable indicator: the comment 'intentionally outside _jobs_lock'
        self.assertIn("intentionally outside _jobs_lock", body,
                      "Comment must document that session_store sync is outside lock")
        comment_idx = body.index("intentionally outside _jobs_lock", lock_idx)
        self.assertLess(lock_idx, comment_idx,
                        "'intentionally outside _jobs_lock' comment must follow the lock block")
        self.assertLess(comment_idx, attach_idx,
                        "attach_active_jobs must appear after the 'outside lock' comment")


# ---------------------------------------------------------------------------
# task-78: job_cancel() out-of-lock writes must be documented
# ---------------------------------------------------------------------------

class TestJobCancelOutOfLockComment(unittest.TestCase):
    """task-78: out-of-lock per-job and marker writes in job_cancel() must be documented."""

    def test_intentionally_outside_lock_comment_present(self) -> None:
        """A comment explaining the out-of-lock writes must be present in job_cancel()."""
        body = _job_cancel_body()
        self.assertIn("Intentionally outside _jobs_lock", body,
                      "job_cancel() must document why per-job writes are outside _jobs_lock")

    def test_idempotent_mentioned_in_comment(self) -> None:
        """The comment must state the writes are idempotent."""
        body = _job_cancel_body()
        self.assertIn("idempotent", body,
                      "job_cancel() out-of-lock comment must explain idempotent safety")

    def test_comment_appears_before_job_file_write(self) -> None:
        """The out-of-lock comment must appear before the self.job_file() write."""
        body = _job_cancel_body()
        comment_idx = body.index("Intentionally outside _jobs_lock")
        job_file_idx = body.index("self.job_file(", comment_idx)
        self.assertLess(comment_idx, job_file_idx,
                        "Out-of-lock comment must appear before self.job_file() write")


# ---------------------------------------------------------------------------
# task-79: jobs_list() must call normalize_job_record()
# ---------------------------------------------------------------------------

class TestJobsListNormalize(unittest.TestCase):
    """task-79: jobs_list() must call normalize_job_record() on each raw job dict."""

    def test_normalize_job_record_imported(self) -> None:
        """normalize_job_record must be imported in admin_gui_server.py."""
        self.assertIn("normalize_job_record", _ADMIN_SRC,
                      "normalize_job_record must be imported from orchestration_state")

    def test_normalize_job_record_called_in_jobs_list(self) -> None:
        """normalize_job_record() must be called inside jobs_list() body."""
        body = _jobs_list_body()
        self.assertIn("normalize_job_record", body,
                      "jobs_list() must call normalize_job_record() on each job dict")

    def test_normalize_called_before_enrich_artifacts(self) -> None:
        """normalize_job_record() must appear before enrich_artifact_cards() in jobs_list()."""
        body = _jobs_list_body()
        norm_idx = body.index("normalize_job_record")
        enrich_idx = body.index("enrich_artifact_cards", norm_idx)
        self.assertLess(norm_idx, enrich_idx,
                        "normalize_job_record() must be called before enrich_artifact_cards()")


class TestJobsListNormalizeBehavioural(unittest.TestCase):
    """Behavioural: jobs_list() must fill missing fields via normalize_job_record()."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_server(self, extra_jobs=None):
        from admin_gui_server import AdminGuiServer, now_iso
        srv = object.__new__(AdminGuiServer)
        tmp = Path(self._tmpdir)
        srv.data_root = tmp
        srv.gui_state_dir = tmp / "gui"
        srv.gui_state_dir.mkdir(parents=True, exist_ok=True)
        srv.jobs_dir = tmp / "jobs"
        srv.jobs_dir.mkdir(parents=True, exist_ok=True)
        srv.session_store = types.SimpleNamespace(attach_active_jobs=lambda *a, **kw: None)
        srv._jobs_lock = threading.Lock()
        jobs = [
            # Minimal job dict — missing 'progress', 'lock_key', 'finished_at', 'version'
            {"job_id": "job_minimal", "status": "done", "kind": "test"},
            # Complete job dict
            {
                "job_id": "job_full", "status": "running", "kind": "test",
                "progress": {"current": 5, "total": 10, "label": "running"},
                "lock_key": "lk1", "artifacts": [],
                "created_at": now_iso(), "updated_at": now_iso(),
                "finished_at": "", "version": "0.32.2",
            },
        ] + (extra_jobs or [])
        jobs_file = srv.jobs_dir / "jobs.json"
        jobs_file.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")
        return srv

    def test_minimal_job_gets_all_schema_fields(self) -> None:
        """A minimal job dict must have all schema fields after jobs_list()."""
        from admin_gui_server import AdminGuiServer
        srv = self._make_server()
        result = AdminGuiServer.jobs_list(srv)
        self.assertTrue(result["ok"])
        minimal = next(j for j in result["jobs"] if j["job_id"] == "job_minimal")
        for field in ("job_id", "kind", "status", "lock_key", "progress",
                      "artifacts", "created_at", "updated_at", "finished_at", "version"):
            with self.subTest(field=field):
                self.assertIn(field, minimal,
                              f"Field '{field}' must be present after normalize_job_record()")

    def test_minimal_job_progress_defaults_to_dict(self) -> None:
        """Missing 'progress' field must default to {'current':0,'total':0,'label':'queued'}."""
        from admin_gui_server import AdminGuiServer
        srv = self._make_server()
        result = AdminGuiServer.jobs_list(srv)
        minimal = next(j for j in result["jobs"] if j["job_id"] == "job_minimal")
        self.assertIsInstance(minimal["progress"], dict,
                              "progress must be a dict after normalize_job_record()")

    def test_full_job_fields_preserved(self) -> None:
        """A complete job dict must not have its fields mutated by normalization."""
        from admin_gui_server import AdminGuiServer
        srv = self._make_server()
        result = AdminGuiServer.jobs_list(srv)
        full = next(j for j in result["jobs"] if j["job_id"] == "job_full")
        self.assertEqual(full["status"], "running")
        self.assertEqual(full["progress"]["current"], 5)
        self.assertEqual(full["progress"]["total"], 10)

    def test_jobs_list_returns_ok_true(self) -> None:
        """jobs_list() must return ok=True."""
        from admin_gui_server import AdminGuiServer
        srv = self._make_server()
        result = AdminGuiServer.jobs_list(srv)
        self.assertTrue(result["ok"])

    def test_jobs_list_returns_all_jobs(self) -> None:
        """jobs_list() must return all jobs from the store."""
        from admin_gui_server import AdminGuiServer
        srv = self._make_server()
        result = AdminGuiServer.jobs_list(srv)
        self.assertEqual(len(result["jobs"]), 2)


if __name__ == "__main__":
    unittest.main()
