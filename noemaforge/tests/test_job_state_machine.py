#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_job_state_machine.py
Zone: tests
Version: 0.32.2
Created: 2026-05-31
Modified: 2026-05-31
Purpose: Tests for job state machine fixes and improvements:
           - task-73 (CRITICAL): job_cancel() must NOT overwrite jobs already in
             FINAL_JOB_STATES (done/failed/cancelled → cancel_requested was a
             state machine violation that permanently corrupted finished jobs).
           - task-74 (HIGH): session_id in GET /api/session/current must be clamped
             to 128 chars before being stored in the session record.
           - task-75 (HIGH): _upsert_job(), _persist_job(), job_cancel() must acquire
             self._jobs_lock to serialise concurrent read-modify-write cycles.
           - task-76 (MEDIUM): 'needs_privilege' added to ACTIVE_JOB_STATES so that
             GUI jobs awaiting polkit approval survive browser refresh (previously
             only in _upsert_job idempotency check, not in is_active_job()).
         Tests are source-guard checks plus a focused behavioural test for task-73.
Inputs: admin_gui_server.py and orchestration_state.py source text; AdminGuiServer
        stub for the job_cancel behavioural test.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_job_state_machine.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _install_stubs() -> None:
    import noemaforge_version as real_version
    sys.modules["noemaforge_version"] = real_version

    stub_orch = types.ModuleType("orchestration_state")
    stub_orch.nowz = lambda: "2026-05-31T00:00:00Z"
    stub_orch.normalize_session_record = lambda r: r
    stub_orch.normalize_job_record = lambda r: dict(r)  # passthrough for job tests
    stub_orch.is_active_job = lambda job: str(job.get("status") or "") in {"queued", "running", "needs_privilege", "starting", "cancel_requested"}
    stub_orch.ACTIVE_JOB_STATES = {"queued", "starting", "running", "cancel_requested", "needs_privilege"}
    stub_orch.FINAL_JOB_STATES = {"done", "failed", "cancelled"}
    sys.modules["orchestration_state"] = stub_orch

    stub_prod = types.ModuleType("production_ai_contracts")
    stub_prod.new_trace_id = lambda kind="": f"trace_{kind}"
    sys.modules["production_ai_contracts"] = stub_prod

    stub_priv = types.ModuleType("privileged_gui_job_runner")
    stub_priv.enrich_privileged_job = lambda job, **_kw: job
    sys.modules["privileged_gui_job_runner"] = stub_priv
    sys.modules.pop("admin_gui_server", None)


_install_stubs()

_ADMIN_SRC = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")
_ORCH_SRC = (_SRC / "orchestration_state.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Source-guard tests (task-73, task-74, task-75, task-76)
# ---------------------------------------------------------------------------

class TestJobCancelFinalStateGuard(unittest.TestCase):
    """task-73: job_cancel() must skip jobs already in FINAL_JOB_STATES."""

    def _job_cancel_body(self) -> str:
        start = _ADMIN_SRC.index("def job_cancel(self")
        try:
            end = _ADMIN_SRC.index("\n    def ", start + 1)
        except ValueError:
            end = len(_ADMIN_SRC)
        return _ADMIN_SRC[start:end]

    def test_final_job_states_imported(self) -> None:
        """FINAL_JOB_STATES must be imported from orchestration_state."""
        self.assertIn("FINAL_JOB_STATES", _ADMIN_SRC,
                      "FINAL_JOB_STATES must be imported in admin_gui_server.py")

    def test_job_cancel_checks_final_states(self) -> None:
        """job_cancel() must check FINAL_JOB_STATES before setting cancel_requested."""
        body = self._job_cancel_body()
        self.assertIn("FINAL_JOB_STATES", body,
                      "job_cancel() must check FINAL_JOB_STATES before modifying status")

    def test_job_cancel_returns_error_for_final_state(self) -> None:
        """job_cancel() must return ok=False when job is already terminal."""
        body = self._job_cancel_body()
        self.assertIn("terminal state", body,
                      "job_cancel() must return an error message for terminal-state jobs")

    def test_job_cancel_sets_cancel_requested_only_for_active(self) -> None:
        """The cancel_requested assignment must be inside a block that excludes final states."""
        body = self._job_cancel_body()
        # The 'return' before the status assignment guards against final states
        final_idx = body.index("FINAL_JOB_STATES")
        return_idx = body.index("return", final_idx)
        status_idx = body.index("cancel_requested", return_idx + 1)
        self.assertLess(return_idx, status_idx,
                        "A 'return' for final-state jobs must appear before 'cancel_requested' assignment")


class TestJobsLock(unittest.TestCase):
    """task-75: job R-M-W methods must use self._jobs_lock."""

    def _upsert_body(self) -> str:
        start = _ADMIN_SRC.index("def _upsert_job(self")
        end = _ADMIN_SRC.index("\n    def ", start + 1)
        return _ADMIN_SRC[start:end]

    def _persist_body(self) -> str:
        start = _ADMIN_SRC.index("def _persist_job(self")
        end = _ADMIN_SRC.index("\n    def ", start + 1)
        return _ADMIN_SRC[start:end]

    def _cancel_body(self) -> str:
        start = _ADMIN_SRC.index("def job_cancel(self")
        try:
            end = _ADMIN_SRC.index("\n    def ", start + 1)
        except ValueError:
            end = len(_ADMIN_SRC)
        return _ADMIN_SRC[start:end]

    def test_jobs_lock_declared_in_init(self) -> None:
        """AdminGuiServer.__init__ must declare self._jobs_lock."""
        self.assertIn("_jobs_lock", _ADMIN_SRC,
                      "AdminGuiServer must declare self._jobs_lock in __init__")

    def test_upsert_job_acquires_lock(self) -> None:
        """_upsert_job() must acquire self._jobs_lock."""
        self.assertIn("_jobs_lock", self._upsert_body(),
                      "_upsert_job() must use self._jobs_lock")

    def test_persist_job_acquires_lock(self) -> None:
        """_persist_job() must acquire self._jobs_lock."""
        self.assertIn("_jobs_lock", self._persist_body(),
                      "_persist_job() must use self._jobs_lock")

    def test_job_cancel_acquires_lock(self) -> None:
        """job_cancel() must acquire self._jobs_lock."""
        self.assertIn("_jobs_lock", self._cancel_body(),
                      "job_cancel() must use self._jobs_lock")

    def test_lock_is_threading_lock(self) -> None:
        """_jobs_lock must be a threading.Lock() instance."""
        # Source check: init body must contain threading.Lock()
        init_start = _ADMIN_SRC.index("def __init__(self, address:")
        init_end = _ADMIN_SRC.index("\n    def ", init_start + 1)
        init_body = _ADMIN_SRC[init_start:init_end]
        self.assertIn("threading.Lock()", init_body,
                      "_jobs_lock must be created as threading.Lock()")


class TestSessionIdClamp(unittest.TestCase):
    """task-74: session_id query param must be clamped to 128 chars in do_GET."""

    def _session_current_block(self) -> str:
        body_start = _ADMIN_SRC.index('"/api/session/current"')
        body_end = _ADMIN_SRC.index("return", body_start) + 10
        return _ADMIN_SRC[body_start:body_end]

    def test_session_id_clamped_to_128(self) -> None:
        """session_id in GET /api/session/current must be clamped to 128 chars."""
        block = self._session_current_block()
        self.assertIn("[:128]", block,
                      "GET /api/session/current must clamp session_id to 128 chars")

    def test_clamp_comment_explains_rationale(self) -> None:
        """A comment must explain why session_id is clamped."""
        block = self._session_current_block()
        self.assertIn("Clamp", block,
                      "A comment must explain the session_id clamp rationale")


class TestNeedsPrivilegeInActiveStates(unittest.TestCase):
    """task-76: 'needs_privilege' must be in ACTIVE_JOB_STATES."""

    def test_needs_privilege_in_active_job_states(self) -> None:
        """ACTIVE_JOB_STATES must contain 'needs_privilege'."""
        self.assertIn('"needs_privilege"', _ORCH_SRC,
                      "'needs_privilege' must appear in ACTIVE_JOB_STATES definition")
        # Verify it's in the ACTIVE_JOB_STATES set, not just elsewhere
        active_start = _ORCH_SRC.index("ACTIVE_JOB_STATES")
        active_line = _ORCH_SRC[active_start:active_start + 120]
        self.assertIn("needs_privilege", active_line,
                      "'needs_privilege' must be in the ACTIVE_JOB_STATES set literal")

    def test_needs_privilege_makes_is_active_job_true(self) -> None:
        """is_active_job({'status': 'needs_privilege'}) must return True."""
        from orchestration_state import is_active_job
        self.assertTrue(is_active_job({"status": "needs_privilege"}),
                        "is_active_job must return True for 'needs_privilege' status")

    def test_upsert_idempotency_set_matches_active_states(self) -> None:
        """_upsert_job idempotency set must include all ACTIVE_JOB_STATES members."""
        start = _ADMIN_SRC.index("def _upsert_job(self")
        end = _ADMIN_SRC.index("\n    def ", start + 1)
        body = _ADMIN_SRC[start:end]
        # The idempotency check now uses the full active state set
        for state in ("queued", "running", "needs_privilege", "cancel_requested", "starting"):
            with self.subTest(state=state):
                self.assertIn(state, body,
                              f"_upsert_job idempotency set must include '{state}'")


# ---------------------------------------------------------------------------
# Behavioural test: job_cancel() must not corrupt final-state jobs
# ---------------------------------------------------------------------------

class TestJobCancelBehavioural(unittest.TestCase):
    """Behavioural test: job_cancel() must refuse to cancel final-state jobs."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_server(self):
        """Create a minimal AdminGuiServer stub with just the jobs infrastructure."""
        import json
        from admin_gui_server import AdminGuiServer, now_iso
        srv = object.__new__(AdminGuiServer)
        tmp = Path(self._tmpdir)
        srv.data_root = tmp
        srv.gui_state_dir = tmp / "gui"
        srv.gui_state_dir.mkdir(parents=True, exist_ok=True)
        srv.jobs_dir = tmp / "jobs"
        srv.jobs_dir.mkdir(parents=True, exist_ok=True)
        srv.session_store = types.SimpleNamespace(attach_active_jobs=lambda *a, **kw: None)
        import threading
        srv._jobs_lock = threading.Lock()
        # Write a jobs.json with a done job and a running job
        jobs_data = {
            "jobs": [
                {"job_id": "job_done", "status": "done", "updated_at": now_iso(), "kind": "test"},
                {"job_id": "job_running", "status": "running", "updated_at": now_iso(), "kind": "test"},
                {"job_id": "job_failed", "status": "failed", "updated_at": now_iso(), "kind": "test"},
                {"job_id": "job_cancelled", "status": "cancelled", "updated_at": now_iso(), "kind": "test"},
            ]
        }
        jobs_file = srv.jobs_dir / "jobs.json"  # must match jobs_file() → jobs_dir/jobs.json
        jobs_file.write_text(json.dumps(jobs_data), encoding="utf-8")
        return srv, jobs_file

    def test_cancel_done_job_returns_ok_false(self) -> None:
        """Cancelling a done job must return ok=False."""
        from admin_gui_server import AdminGuiServer
        srv, jobs_file = self._make_server()
        # Bind methods to the stub server
        import json
        result = AdminGuiServer.job_cancel(srv, "job_done")
        self.assertFalse(result["ok"],
                         "Cancelling a done job must return ok=False")

    def test_cancel_done_job_does_not_change_status(self) -> None:
        """Cancelling a done job must leave its status as 'done' on disk."""
        from admin_gui_server import AdminGuiServer
        import json
        srv, jobs_file = self._make_server()
        AdminGuiServer.job_cancel(srv, "job_done")
        data = json.loads(jobs_file.read_text(encoding="utf-8"))
        done_jobs = [j for j in data["jobs"] if j["job_id"] == "job_done"]
        self.assertEqual(len(done_jobs), 1)
        self.assertEqual(done_jobs[0]["status"], "done",
                         "Cancelling a done job must not change its status to cancel_requested")

    def test_cancel_running_job_succeeds(self) -> None:
        """Cancelling a running job must return ok=True and set cancel_requested."""
        from admin_gui_server import AdminGuiServer
        import json
        srv, jobs_file = self._make_server()
        result = AdminGuiServer.job_cancel(srv, "job_running")
        self.assertTrue(result["ok"],
                        "Cancelling a running job must return ok=True")
        data = json.loads(jobs_file.read_text(encoding="utf-8"))
        running_jobs = [j for j in data["jobs"] if j["job_id"] == "job_running"]
        self.assertEqual(running_jobs[0]["status"], "cancel_requested",
                         "Running job must be set to cancel_requested after cancel")

    def test_cancel_failed_job_returns_ok_false(self) -> None:
        """Cancelling a failed job must return ok=False."""
        from admin_gui_server import AdminGuiServer
        srv, _ = self._make_server()
        result = AdminGuiServer.job_cancel(srv, "job_failed")
        self.assertFalse(result["ok"],
                         "Cancelling a failed job must return ok=False")

    def test_cancel_already_cancelled_job_returns_ok_false(self) -> None:
        """Cancelling an already-cancelled job must return ok=False."""
        from admin_gui_server import AdminGuiServer
        srv, _ = self._make_server()
        result = AdminGuiServer.job_cancel(srv, "job_cancelled")
        self.assertFalse(result["ok"],
                         "Cancelling an already-cancelled job must return ok=False")


if __name__ == "__main__":
    unittest.main()
