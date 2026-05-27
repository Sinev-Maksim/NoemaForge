#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_job_manager.py
Zone: test
Version: 0.32.2
Created: 2026-05-27
Modified: 2026-05-27
Purpose: TDD tests for JobManager — file-backed job tracking with PID, cancel, stdout/stderr tails.
Inputs: job_manager.JobManager, orchestration_state constants.
Outputs: test pass/fail.
Side effects: Creates and removes temporary directories.
Tests: python3 -m unittest noemaforge/tests/test_job_manager.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Ensure noemaforge/src is on path.
_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from job_manager import JobManager  # noqa: E402
from orchestration_state import ACTIVE_JOB_STATES, FINAL_JOB_STATES  # noqa: E402


class TestJobManagerCreate(unittest.TestCase):
    """JobManager.create() returns a normalized record and persists it."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.jm = JobManager(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_create_returns_dict(self) -> None:
        job = self.jm.create("model-selection")
        self.assertIsInstance(job, dict)

    def test_create_sets_kind(self) -> None:
        job = self.jm.create("vault-reinventory")
        self.assertEqual(job["kind"], "vault-reinventory")

    def test_create_initial_status_queued(self) -> None:
        job = self.jm.create("model-selection")
        self.assertEqual(job["status"], "queued")

    def test_create_has_job_id(self) -> None:
        job = self.jm.create("model-selection")
        self.assertIn("job_id", job)
        self.assertTrue(job["job_id"].startswith("job_"))

    def test_create_has_required_fields(self) -> None:
        job = self.jm.create("test-job")
        required = {
            "job_id", "kind", "status", "lock_key", "idempotency_key",
            "pid", "pgid", "cancellation_flag",
            "progress", "artifacts",
            "stdout_tail", "stderr_tail",
            "command", "trace_id",
            "created_at", "updated_at", "finished_at",
            "version",
        }
        missing = required - job.keys()
        self.assertFalse(missing, f"Missing fields: {missing}")

    def test_create_pid_zero_by_default(self) -> None:
        job = self.jm.create("model-selection")
        self.assertEqual(job["pid"], 0)
        self.assertEqual(job["pgid"], 0)

    def test_create_cancellation_flag_false(self) -> None:
        job = self.jm.create("model-selection")
        self.assertFalse(job["cancellation_flag"])

    def test_create_progress_shape(self) -> None:
        job = self.jm.create("model-selection")
        self.assertIsInstance(job["progress"], dict)
        self.assertIn("current", job["progress"])
        self.assertIn("total", job["progress"])
        self.assertIn("label", job["progress"])

    def test_create_persists_to_jobs_json(self) -> None:
        job = self.jm.create("model-selection")
        jobs_file = Path(self._td.name) / "jobs.json"
        self.assertTrue(jobs_file.exists())
        data = json.loads(jobs_file.read_text(encoding="utf-8"))
        ids = [j["job_id"] for j in data["jobs"]]
        self.assertIn(job["job_id"], ids)

    def test_create_persists_individual_file(self) -> None:
        job = self.jm.create("model-selection")
        job_file = Path(self._td.name) / f"{job['job_id']}.json"
        self.assertTrue(job_file.exists())

    def test_create_with_command(self) -> None:
        job = self.jm.create("model-selection", command="noemaforge model-selection run")
        self.assertEqual(job["command"], "noemaforge model-selection run")

    def test_create_with_lock_key(self) -> None:
        job = self.jm.create("model-selection", lock_key="model-selection-lock")
        self.assertEqual(job["lock_key"], "model-selection-lock")

    def test_create_version_matches_runtime(self) -> None:
        from noemaforge_version import RUNTIME_VERSION
        job = self.jm.create("model-selection")
        self.assertEqual(job["version"], RUNTIME_VERSION)


class TestJobManagerIdempotency(unittest.TestCase):
    """_upsert / idempotency_key deduplication."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.jm = JobManager(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_idempotent_create_returns_same_job(self) -> None:
        key = "vault-reinventory"
        j1 = self.jm.create("vault-reinventory", idempotency_key=key)
        j2 = self.jm.create("vault-reinventory", idempotency_key=key)
        self.assertEqual(j1["job_id"], j2["job_id"])

    def test_idempotent_only_matches_active_states(self) -> None:
        key = "model-selection-k1"
        j1 = self.jm.create("model-selection", idempotency_key=key)
        # Mark done first.
        self.jm.finish(j1["job_id"], success=True)
        # A new job should be created.
        j2 = self.jm.create("model-selection", idempotency_key=key)
        self.assertNotEqual(j1["job_id"], j2["job_id"])

    def test_no_idempotency_key_always_new(self) -> None:
        j1 = self.jm.create("model-selection")
        j2 = self.jm.create("model-selection")
        self.assertNotEqual(j1["job_id"], j2["job_id"])


class TestJobManagerGet(unittest.TestCase):
    """get() and list methods."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.jm = JobManager(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_get_existing_job(self) -> None:
        job = self.jm.create("test-job")
        fetched = self.jm.get(job["job_id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["job_id"], job["job_id"])  # type: ignore[index]

    def test_get_missing_returns_none(self) -> None:
        result = self.jm.get("job_nonexistent")
        self.assertIsNone(result)

    def test_list_all_includes_created_job(self) -> None:
        job = self.jm.create("test-job")
        all_jobs = self.jm.list_all()
        ids = [j["job_id"] for j in all_jobs]
        self.assertIn(job["job_id"], ids)

    def test_list_active_returns_active(self) -> None:
        job = self.jm.create("test-job")
        active = self.jm.list_active()
        ids = [j["job_id"] for j in active]
        self.assertIn(job["job_id"], ids)

    def test_list_active_excludes_done(self) -> None:
        job = self.jm.create("test-job")
        self.jm.finish(job["job_id"], success=True)
        active = self.jm.list_active()
        ids = [j["job_id"] for j in active]
        self.assertNotIn(job["job_id"], ids)


class TestJobManagerUpdateStatus(unittest.TestCase):
    """update_status() transitions."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.jm = JobManager(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_update_status_running(self) -> None:
        job = self.jm.create("model-selection")
        updated = self.jm.update_status(job["job_id"], "running")
        self.assertIsNotNone(updated)
        self.assertEqual(updated["status"], "running")  # type: ignore[index]

    def test_update_status_persists(self) -> None:
        job = self.jm.create("model-selection")
        self.jm.update_status(job["job_id"], "starting")
        fetched = self.jm.get(job["job_id"])
        self.assertEqual(fetched["status"], "starting")  # type: ignore[index]

    def test_update_status_updates_progress(self) -> None:
        job = self.jm.create("model-selection")
        updated = self.jm.update_status(
            job["job_id"], "running",
            progress={"current": 3, "total": 10, "label": "running step 3"},
        )
        self.assertEqual(updated["progress"]["current"], 3)  # type: ignore[index]

    def test_update_missing_job_returns_none(self) -> None:
        result = self.jm.update_status("job_nonexistent", "running")
        self.assertIsNone(result)

    def test_update_status_invalid_ignored(self) -> None:
        """Unknown status strings should still be accepted (callers validate)."""
        job = self.jm.create("test")
        updated = self.jm.update_status(job["job_id"], "unknown_status")
        self.assertEqual(updated["status"], "unknown_status")  # type: ignore[index]


class TestJobManagerPID(unittest.TestCase):
    """set_pid() tracks process group."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.jm = JobManager(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_set_pid_stores_pid_and_pgid(self) -> None:
        job = self.jm.create("model-selection")
        updated = self.jm.set_pid(job["job_id"], pid=12345, pgid=12344)
        self.assertIsNotNone(updated)
        self.assertEqual(updated["pid"], 12345)  # type: ignore[index]
        self.assertEqual(updated["pgid"], 12344)  # type: ignore[index]

    def test_set_pid_persists(self) -> None:
        job = self.jm.create("model-selection")
        self.jm.set_pid(job["job_id"], pid=99999, pgid=99998)
        fetched = self.jm.get(job["job_id"])
        self.assertEqual(fetched["pid"], 99999)  # type: ignore[index]

    def test_set_pid_missing_returns_none(self) -> None:
        result = self.jm.set_pid("job_nope", pid=1, pgid=1)
        self.assertIsNone(result)


class TestJobManagerCancel(unittest.TestCase):
    """cancel() sets cancellation_flag and status."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.jm = JobManager(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_cancel_active_job_sets_flag(self) -> None:
        job = self.jm.create("model-selection")
        self.jm.update_status(job["job_id"], "running")
        cancelled = self.jm.cancel(job["job_id"])
        self.assertIsNotNone(cancelled)
        self.assertTrue(cancelled["cancellation_flag"])  # type: ignore[index]

    def test_cancel_sets_status_cancel_requested(self) -> None:
        job = self.jm.create("model-selection")
        self.jm.update_status(job["job_id"], "running")
        cancelled = self.jm.cancel(job["job_id"])
        self.assertEqual(cancelled["status"], "cancel_requested")  # type: ignore[index]

    def test_cancel_already_done_is_noop(self) -> None:
        job = self.jm.create("model-selection")
        self.jm.finish(job["job_id"], success=True)
        result = self.jm.cancel(job["job_id"])
        # Should return None (already final) or the unchanged job.
        if result is not None:
            self.assertEqual(result["status"], "done")
            self.assertFalse(result["cancellation_flag"])

    def test_cancel_missing_returns_none(self) -> None:
        result = self.jm.cancel("job_nope")
        self.assertIsNone(result)

    def test_cancel_persists(self) -> None:
        job = self.jm.create("model-selection")
        self.jm.update_status(job["job_id"], "running")
        self.jm.cancel(job["job_id"])
        fetched = self.jm.get(job["job_id"])
        self.assertTrue(fetched["cancellation_flag"])  # type: ignore[index]


class TestJobManagerOutput(unittest.TestCase):
    """append_output() builds bounded stdout/stderr tails."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.jm = JobManager(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_append_stdout(self) -> None:
        job = self.jm.create("model-selection")
        updated = self.jm.append_output(job["job_id"], stdout="step 1 done\n")
        self.assertIn("step 1 done", updated["stdout_tail"])  # type: ignore[index]

    def test_append_stderr(self) -> None:
        job = self.jm.create("model-selection")
        updated = self.jm.append_output(job["job_id"], stderr="WARNING: something\n")
        self.assertIn("WARNING:", updated["stderr_tail"])  # type: ignore[index]

    def test_output_accumulates(self) -> None:
        job = self.jm.create("model-selection")
        self.jm.append_output(job["job_id"], stdout="line1\n")
        updated = self.jm.append_output(job["job_id"], stdout="line2\n")
        self.assertIn("line1", updated["stdout_tail"])  # type: ignore[index]
        self.assertIn("line2", updated["stdout_tail"])  # type: ignore[index]

    def test_output_bounded_by_max_tail(self) -> None:
        job = self.jm.create("model-selection")
        big_chunk = "x" * 1000
        # Append enough to exceed a small max_tail.
        for _ in range(5):
            self.jm.append_output(job["job_id"], stdout=big_chunk, max_tail=2000)
        fetched = self.jm.get(job["job_id"])
        self.assertLessEqual(len(fetched["stdout_tail"]), 2000 + 100)  # type: ignore[index]

    def test_append_missing_returns_none(self) -> None:
        result = self.jm.append_output("job_nope", stdout="hello")
        self.assertIsNone(result)


class TestJobManagerFinish(unittest.TestCase):
    """finish() marks job done/failed with finished_at timestamp."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.jm = JobManager(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_finish_success_sets_done(self) -> None:
        job = self.jm.create("model-selection")
        finished = self.jm.finish(job["job_id"], success=True)
        self.assertEqual(finished["status"], "done")  # type: ignore[index]

    def test_finish_failure_sets_failed(self) -> None:
        job = self.jm.create("model-selection")
        finished = self.jm.finish(job["job_id"], success=False)
        self.assertEqual(finished["status"], "failed")  # type: ignore[index]

    def test_finish_sets_finished_at(self) -> None:
        job = self.jm.create("model-selection")
        finished = self.jm.finish(job["job_id"], success=True)
        self.assertTrue(finished["finished_at"])  # type: ignore[index]

    def test_finish_with_artifacts(self) -> None:
        job = self.jm.create("model-selection")
        arts = [{"label": "Report", "path": "/tmp/report.html"}]
        finished = self.jm.finish(job["job_id"], success=True, artifacts=arts)
        self.assertEqual(len(finished["artifacts"]), 1)  # type: ignore[index]

    def test_finish_removes_from_active(self) -> None:
        job = self.jm.create("model-selection")
        self.jm.finish(job["job_id"], success=True)
        active_ids = [j["job_id"] for j in self.jm.list_active()]
        self.assertNotIn(job["job_id"], active_ids)

    def test_finish_still_in_all(self) -> None:
        job = self.jm.create("model-selection")
        self.jm.finish(job["job_id"], success=True)
        all_ids = [j["job_id"] for j in self.jm.list_all()]
        self.assertIn(job["job_id"], all_ids)

    def test_finish_missing_returns_none(self) -> None:
        result = self.jm.finish("job_nope", success=True)
        self.assertIsNone(result)


class TestJobManagerPersistenceRoundtrip(unittest.TestCase):
    """Reload JobManager from same dir and see same jobs."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_roundtrip_get(self) -> None:
        jm1 = JobManager(Path(self._td.name))
        job = jm1.create("model-selection", command="run-me")
        jm2 = JobManager(Path(self._td.name))
        fetched = jm2.get(job["job_id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["command"], "run-me")  # type: ignore[index]

    def test_roundtrip_list_all(self) -> None:
        jm1 = JobManager(Path(self._td.name))
        j1 = jm1.create("model-selection")
        j2 = jm1.create("vault-reinventory")
        jm2 = JobManager(Path(self._td.name))
        all_ids = {j["job_id"] for j in jm2.list_all()}
        self.assertIn(j1["job_id"], all_ids)
        self.assertIn(j2["job_id"], all_ids)


if __name__ == "__main__":
    unittest.main()
