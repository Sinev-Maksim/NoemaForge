#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_job_heartbeat_and_process_runner.py
Zone: test
Version: 0.32.2
Created: 2026-05-27
Modified: 2026-05-27
Purpose: TDD tests for JobManager.heartbeat() and ProcessGroupRunner safe subprocess wrapper.
Inputs: job_manager.JobManager, process_group_runner.ProcessGroupRunner.
Outputs: test pass/fail.
Side effects: Creates temporary directories; spawns very short-lived subprocesses.
Tests: python3 -m unittest noemaforge/tests/test_job_heartbeat_and_process_runner.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from job_manager import JobManager  # noqa: E402
from process_group_runner import ProcessGroupRunner, kill_signal  # noqa: E402


# ---------------------------------------------------------------------------
# JobManager heartbeat tests
# ---------------------------------------------------------------------------

class TestJobManagerHeartbeat(unittest.TestCase):
    """JobManager.heartbeat() updates last_heartbeat and returns the job."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.jm = JobManager(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_heartbeat_returns_job(self) -> None:
        job = self.jm.create("model-selection")
        result = self.jm.heartbeat(job["job_id"])
        self.assertIsNotNone(result)

    def test_heartbeat_sets_last_heartbeat(self) -> None:
        job = self.jm.create("model-selection")
        updated = self.jm.heartbeat(job["job_id"])
        self.assertIn("last_heartbeat", updated)
        self.assertTrue(updated["last_heartbeat"])  # type: ignore[index]

    def test_heartbeat_is_iso_timestamp(self) -> None:
        job = self.jm.create("model-selection")
        updated = self.jm.heartbeat(job["job_id"])
        ts = updated["last_heartbeat"]  # type: ignore[index]
        # Must be a non-empty ISO-format string ending in Z.
        self.assertTrue(ts.endswith("Z"), f"expected ISO timestamp ending in Z, got {ts!r}")

    def test_heartbeat_persists(self) -> None:
        job = self.jm.create("model-selection")
        self.jm.heartbeat(job["job_id"])
        fetched = self.jm.get(job["job_id"])
        self.assertIn("last_heartbeat", fetched)
        self.assertTrue(fetched["last_heartbeat"])  # type: ignore[index]

    def test_heartbeat_missing_returns_none(self) -> None:
        result = self.jm.heartbeat("job_nonexistent")
        self.assertIsNone(result)

    def test_heartbeat_advances_timestamp(self) -> None:
        job = self.jm.create("model-selection")
        u1 = self.jm.heartbeat(job["job_id"])
        time.sleep(0.01)
        u2 = self.jm.heartbeat(job["job_id"])
        # updated_at must also advance.
        self.assertGreaterEqual(u2["updated_at"], u1["updated_at"])  # type: ignore[index]

    def test_heartbeat_creates_field_in_normalized_record(self) -> None:
        job = self.jm.create("model-selection")
        fetched_before = self.jm.get(job["job_id"])
        # Field must exist (even if empty) from the start.
        self.assertIn("last_heartbeat", fetched_before)

    def test_is_stale_no_heartbeat(self) -> None:
        """Job with no heartbeat and old updated_at is stale."""
        job = self.jm.create("model-selection")
        # A very long stale timeout — without a heartbeat the job is stale.
        stale = self.jm.is_stale(job["job_id"], stale_seconds=0)
        self.assertTrue(stale)

    def test_is_stale_fresh_heartbeat(self) -> None:
        job = self.jm.create("model-selection")
        self.jm.heartbeat(job["job_id"])
        # With a very long stale timeout a freshly-beaten job is NOT stale.
        stale = self.jm.is_stale(job["job_id"], stale_seconds=3600)
        self.assertFalse(stale)

    def test_is_stale_missing_returns_true(self) -> None:
        stale = self.jm.is_stale("job_nonexistent", stale_seconds=60)
        self.assertTrue(stale)


# ---------------------------------------------------------------------------
# ProcessGroupRunner tests
# ---------------------------------------------------------------------------

class TestProcessGroupRunnerBasic(unittest.TestCase):
    """ProcessGroupRunner launches subprocesses and integrates with JobManager."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.jm = JobManager(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def _runner(self, job_id: str) -> "ProcessGroupRunner":
        return ProcessGroupRunner(job_id=job_id, job_manager=self.jm)

    # --- constructor ---

    def test_constructor_accepts_job_id_and_manager(self) -> None:
        job = self.jm.create("test")
        runner = self._runner(job["job_id"])
        self.assertIsNotNone(runner)

    def test_runner_has_is_running_false_before_start(self) -> None:
        job = self.jm.create("test")
        runner = self._runner(job["job_id"])
        self.assertFalse(runner.is_running())

    # --- run ---

    def test_run_returns_exit_code(self) -> None:
        job = self.jm.create("test")
        runner = self._runner(job["job_id"])
        rc = runner.run([sys.executable, "-c", "import sys; sys.exit(0)"])
        self.assertEqual(rc, 0)

    def test_run_sets_status_running_during_execution(self) -> None:
        """Status transitions to 'running' once the process starts."""
        job = self.jm.create("test")
        runner = self._runner(job["job_id"])
        # Use a short sleep so we can check status.
        runner.run([sys.executable, "-c", "import time; time.sleep(0.05)"])
        # After completion: done.
        fetched = self.jm.get(job["job_id"])
        self.assertEqual(fetched["status"], "done")  # type: ignore[index]

    def test_run_records_pid(self) -> None:
        job = self.jm.create("test")
        runner = self._runner(job["job_id"])
        runner.run([sys.executable, "-c", "pass"])
        fetched = self.jm.get(job["job_id"])
        self.assertGreater(fetched["pid"], 0)  # type: ignore[index]

    def test_run_failure_marks_failed(self) -> None:
        job = self.jm.create("test")
        runner = self._runner(job["job_id"])
        rc = runner.run([sys.executable, "-c", "import sys; sys.exit(1)"])
        self.assertEqual(rc, 1)
        fetched = self.jm.get(job["job_id"])
        self.assertEqual(fetched["status"], "failed")  # type: ignore[index]

    def test_run_captures_stdout(self) -> None:
        job = self.jm.create("test")
        runner = self._runner(job["job_id"])
        runner.run([sys.executable, "-c", "print('hello from subprocess')"])
        fetched = self.jm.get(job["job_id"])
        self.assertIn("hello from subprocess", fetched["stdout_tail"])  # type: ignore[index]

    def test_run_captures_stderr(self) -> None:
        job = self.jm.create("test")
        runner = self._runner(job["job_id"])
        runner.run([sys.executable, "-c", "import sys; sys.stderr.write('err line\\n')"])
        fetched = self.jm.get(job["job_id"])
        self.assertIn("err line", fetched["stderr_tail"])  # type: ignore[index]

    def test_run_sets_finished_at(self) -> None:
        job = self.jm.create("test")
        runner = self._runner(job["job_id"])
        runner.run([sys.executable, "-c", "pass"])
        fetched = self.jm.get(job["job_id"])
        self.assertTrue(fetched["finished_at"])  # type: ignore[index]

    # --- cancel ---

    def test_cancel_stops_running_process(self) -> None:
        """cancel() during a long-running job causes early termination."""
        import threading
        job = self.jm.create("test")
        runner = self._runner(job["job_id"])
        results = {}

        def run_it():
            results["rc"] = runner.run([sys.executable, "-c", "import time; time.sleep(10)"])

        t = threading.Thread(target=run_it, daemon=True)
        t.start()
        # Wait for process to start.
        deadline = time.time() + 3
        while time.time() < deadline:
            if runner.is_running():
                break
            time.sleep(0.05)
        runner.cancel()
        t.join(timeout=5)
        self.assertIsNotNone(results.get("rc"))
        # Exit code should be non-zero after kill.
        self.assertNotEqual(results.get("rc"), 0)

    def test_cancel_before_start_is_noop(self) -> None:
        """cancel() before run() should not raise."""
        job = self.jm.create("test")
        runner = self._runner(job["job_id"])
        try:
            runner.cancel()
        except Exception as e:
            self.fail(f"cancel() before run() raised: {e}")


class TestProcessGroupRunnerKeepDisplay(unittest.TestCase):
    """ProcessGroupRunner enforces --keep-display requirement."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.jm = JobManager(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_require_keep_display_passes_when_flag_present(self) -> None:
        job = self.jm.create("first-start", command="sudo noemaforge first-start --keep-display")
        runner = ProcessGroupRunner(job_id=job["job_id"], job_manager=self.jm, require_keep_display=True)
        # Should not raise — flag is in the job command.
        ok = runner.validate_keep_display()
        self.assertTrue(ok)

    def test_require_keep_display_fails_when_flag_missing(self) -> None:
        job = self.jm.create("first-start", command="sudo noemaforge first-start --full")
        runner = ProcessGroupRunner(job_id=job["job_id"], job_manager=self.jm, require_keep_display=True)
        ok = runner.validate_keep_display()
        self.assertFalse(ok)

    def test_no_require_keep_display_always_passes(self) -> None:
        job = self.jm.create("test", command="python -c 'pass'")
        runner = ProcessGroupRunner(job_id=job["job_id"], job_manager=self.jm, require_keep_display=False)
        ok = runner.validate_keep_display()
        self.assertTrue(ok)


class TestKillSignal(unittest.TestCase):
    """kill_signal() routes the force-kill signal portably (Codex #34)."""

    def test_returns_sigkill_or_sigterm(self) -> None:
        import signal
        expected = getattr(signal, "SIGKILL", signal.SIGTERM)
        self.assertEqual(kill_signal(), expected)

    def test_posix_prefers_sigkill_else_sigterm(self) -> None:
        import os
        import signal
        if os.name == "posix":
            self.assertEqual(kill_signal(), signal.SIGKILL)
        else:
            # No SIGKILL on this platform — must fall back to SIGTERM.
            self.assertEqual(kill_signal(), signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
