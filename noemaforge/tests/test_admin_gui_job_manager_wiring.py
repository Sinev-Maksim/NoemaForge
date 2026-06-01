#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_gui_job_manager_wiring.py
Zone: test
Version: 0.32.2
Created: 2026-05-27
Modified: 2026-05-27
Purpose: TDD tests for wiring JobManager into AdminGuiServer job methods.
Inputs: admin_gui_server.AdminGuiServer, job_manager.JobManager.
Outputs: test pass/fail.
Side effects: Creates and removes temporary directories.
Tests: python3 -m unittest noemaforge/tests/test_admin_gui_job_manager_wiring.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from admin_gui_server import AdminGuiServer  # noqa: E402
from job_manager import JobManager  # noqa: E402
from noemaforge_version import RUNTIME_VERSION  # noqa: E402


def _make_server(td: Path) -> AdminGuiServer:
    """Construct AdminGuiServer stub with job_manager wired in."""
    srv = object.__new__(AdminGuiServer)
    srv.jobs_dir = td / "jobs"
    srv.jobs_dir.mkdir(parents=True, exist_ok=True)
    srv.job_manager = JobManager(srv.jobs_dir)
    return srv


class TestCreateJobUsesJobManager(unittest.TestCase):
    """create_job() persists via job_manager and returns normalized record."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.srv = _make_server(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_create_job_returns_dict_with_job_id(self) -> None:
        job = self.srv.create_job("model-selection")
        self.assertIn("job_id", job)
        self.assertTrue(job["job_id"].startswith("job_"))

    def test_create_job_persists_via_job_manager(self) -> None:
        job = self.srv.create_job("vault-reinventory")
        fetched = self.srv.job_manager.get(job["job_id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["kind"], "vault-reinventory")  # type: ignore[index]

    def test_create_job_idempotency_key_deduplicates(self) -> None:
        key = "model-selection-continue:full_composite:4"
        j1 = self.srv.create_job("model_selection_continue", idempotency_key=key)
        j2 = self.srv.create_job("model_selection_continue", idempotency_key=key)
        self.assertEqual(j1["job_id"], j2["job_id"])

    def test_create_job_needs_privilege_deduplicates(self) -> None:
        """needs_privilege status jobs must participate in idempotency checks."""
        key = "vault-reinventory"
        j1 = self.srv.create_job("vault_reinventory", status="needs_privilege", idempotency_key=key)
        j2 = self.srv.create_job("vault_reinventory", status="needs_privilege", idempotency_key=key)
        self.assertEqual(j1["job_id"], j2["job_id"])

    def test_create_job_no_idempotency_always_new(self) -> None:
        j1 = self.srv.create_job("test-job")
        j2 = self.srv.create_job("test-job")
        self.assertNotEqual(j1["job_id"], j2["job_id"])

    def test_create_job_stores_command(self) -> None:
        job = self.srv.create_job("model-selection", command="sudo noemaforge first-start --normal --keep-display")
        self.assertIn("keep-display", job["command"])

    def test_create_job_has_new_pid_pgid_fields(self) -> None:
        """create_job() now includes JobManager fields in the record."""
        job = self.srv.create_job("model-selection")
        self.assertIn("pid", job)
        self.assertIn("pgid", job)
        self.assertIn("cancellation_flag", job)
        self.assertIn("stdout_tail", job)
        self.assertIn("stderr_tail", job)

    def test_create_job_version_matches_runtime(self) -> None:
        job = self.srv.create_job("model-selection")
        self.assertEqual(job["version"], RUNTIME_VERSION)


class TestPersistJobUsesJobManager(unittest.TestCase):
    """_persist_job() updates the record via job_manager."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.srv = _make_server(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_persist_job_updates_status(self) -> None:
        job = self.srv.create_job("model-selection")
        job["status"] = "running"
        updated = self.srv._persist_job(job)
        fetched = self.srv.job_manager.get(updated["job_id"])
        self.assertEqual(fetched["status"], "running")  # type: ignore[index]

    def test_persist_job_preserves_extra_fields(self) -> None:
        """Extra fields added by enrich_privileged_job must survive persist."""
        job = self.srv.create_job("vault-reinventory")
        job["privileged_runner_command"] = "sudo pkexec ..."
        job["privileged_steps"] = ["step-a", "step-b"]
        updated = self.srv._persist_job(job)
        fetched = self.srv.job_manager.get(updated["job_id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.get("privileged_runner_command"), "sudo pkexec ...")  # type: ignore[index]

    def test_persist_job_writes_jobs_json(self) -> None:
        job = self.srv.create_job("test-job")
        self.srv._persist_job(job)
        jobs_file = self.srv.jobs_dir / "jobs.json"
        self.assertTrue(jobs_file.exists())


class TestJobsListUsesJobManager(unittest.TestCase):
    """jobs_list() returns ok+version+jobs from job_manager."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.srv = _make_server(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_jobs_list_ok(self) -> None:
        result = self.srv.jobs_list()
        self.assertTrue(result["ok"])

    def test_jobs_list_has_version(self) -> None:
        result = self.srv.jobs_list()
        self.assertEqual(result["version"], RUNTIME_VERSION)

    def test_jobs_list_has_jobs_key(self) -> None:
        result = self.srv.jobs_list()
        self.assertIn("jobs", result)

    def test_jobs_list_includes_created_job(self) -> None:
        job = self.srv.create_job("model-selection")
        result = self.srv.jobs_list()
        ids = [j["job_id"] for j in result["jobs"]]
        self.assertIn(job["job_id"], ids)

    def test_jobs_list_empty_when_no_jobs(self) -> None:
        result = self.srv.jobs_list()
        self.assertEqual(result["jobs"], [])


class TestJobGetUsesJobManager(unittest.TestCase):
    """job_get() returns a job by id via job_manager."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.srv = _make_server(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_job_get_found(self) -> None:
        job = self.srv.create_job("model-selection")
        result = self.srv.job_get(job["job_id"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["job"]["job_id"], job["job_id"])

    def test_job_get_not_found(self) -> None:
        result = self.srv.job_get("job_nonexistent")
        self.assertFalse(result["ok"])
        self.assertIn("error", result)

    def test_job_get_has_version(self) -> None:
        job = self.srv.create_job("test")
        result = self.srv.job_get(job["job_id"])
        self.assertEqual(result["version"], RUNTIME_VERSION)


class TestJobCancelUsesJobManager(unittest.TestCase):
    """job_cancel() uses job_manager.cancel()."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.srv = _make_server(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_job_cancel_active_job(self) -> None:
        job = self.srv.create_job("model-selection")
        result = self.srv.job_cancel(job["job_id"])
        self.assertTrue(result["ok"])

    def test_job_cancel_sets_status(self) -> None:
        job = self.srv.create_job("model-selection")
        self.srv.job_cancel(job["job_id"])
        fetched = self.srv.job_manager.get(job["job_id"])
        # Cancelled jobs should be in a cancel-related state.
        self.assertIn(fetched["status"], {"cancelled", "cancel_requested"})  # type: ignore[index]

    def test_job_cancel_not_found(self) -> None:
        result = self.srv.job_cancel("job_nonexistent")
        self.assertFalse(result["ok"])

    def test_job_cancel_has_version(self) -> None:
        job = self.srv.create_job("test")
        result = self.srv.job_cancel(job["job_id"])
        self.assertEqual(result["version"], RUNTIME_VERSION)


class TestAdminGuiServerSourceWiresJobManager(unittest.TestCase):
    """Static source checks confirming job_manager is imported and wired."""

    def setUp(self) -> None:
        self._src = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")

    def test_imports_job_manager(self) -> None:
        self.assertIn("from job_manager import JobManager", self._src)

    def test_init_creates_job_manager(self) -> None:
        self.assertIn("self.job_manager = JobManager", self._src)

    def test_create_job_calls_job_manager(self) -> None:
        self.assertIn("self.job_manager.create", self._src)

    def test_job_cancel_calls_job_manager(self) -> None:
        self.assertIn("self.job_manager.cancel", self._src)


if __name__ == "__main__":
    unittest.main()
