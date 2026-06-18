#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/process_group_runner.py
Zone: runtime/orchestration
Version: 0.32.2
Created: 2026-05-27
Modified: 2026-05-27
Purpose: Safe subprocess wrapper for heavy NoemaForge jobs; runs in its own process group,
         captures stdout/stderr into JobManager tail buffers, and supports graceful cancel.
Inputs: job_id, job_manager.JobManager instance, command list.
Outputs: integer exit code; side effects through JobManager (status, pid, pgid, tails, finished_at).
Side effects: Spawns a subprocess; writes to JobManager files.
Tests: python3 -m unittest noemaforge/tests/test_job_heartbeat_and_process_runner.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from job_manager import JobManager

# Time in seconds between SIGTERM and SIGKILL on cancel (Linux/macOS only).
_GRACEFUL_TIMEOUT = 5


def _is_posix() -> bool:
    return os.name == "posix"


def kill_signal() -> int:
    """Force-kill signal for the host: ``SIGKILL`` where defined, else ``SIGTERM``.

    Windows has no ``signal.SIGKILL``; routing the fallback through one helper keeps
    the cross-platform process-kill call sites consistent (Codex #34).
    """
    return getattr(signal, "SIGKILL", signal.SIGTERM)


class ProcessGroupRunner:
    """Launch a subprocess in its own process group and integrate with JobManager.

    On POSIX systems the child process starts a new process group (via
    ``os.setsid``) so that sending SIGTERM/SIGKILL to the group terminates
    the entire child tree.  On Windows, process groups are not available;
    the child is terminated directly via ``Popen.terminate()``/``kill()``.

    Usage::

        runner = ProcessGroupRunner(job_id=job["job_id"], job_manager=jm)
        rc = runner.run(["sudo", "noemaforge", "first-start", "--keep-display"])

    The runner updates the job record in ``job_manager`` throughout execution:

    - ``status`` → ``"running"`` on start, ``"done"`` or ``"failed"`` on finish
    - ``pid`` / ``pgid`` → OS values after process starts
    - ``stdout_tail`` / ``stderr_tail`` → captured output (bounded)
    - ``finished_at`` → set when process exits
    """

    def __init__(
        self,
        *,
        job_id: str,
        job_manager: "JobManager",
        require_keep_display: bool = False,
        tail_limit: int = 4096,
    ) -> None:
        self._job_id = job_id
        self._jm = job_manager
        self._require_keep_display = require_keep_display
        self._tail_limit = tail_limit
        self._proc: Optional[subprocess.Popen] = None  # type: ignore[type-arg]
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def validate_keep_display(self) -> bool:
        """Return True unless require_keep_display=True AND the job command lacks --keep-display."""
        if not self._require_keep_display:
            return True
        job = self._jm.get(self._job_id)
        if job is None:
            return False
        command = str(job.get("command") or "")
        return "--keep-display" in command

    def is_running(self) -> bool:
        """Return True when the subprocess is alive."""
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def run(self, cmd: List[str], *, env: Optional[dict] = None, timeout: Optional[int] = None) -> int:  # type: ignore[type-arg]
        """Launch *cmd*, stream output into JobManager tail buffers, return exit code.

        Blocks until the subprocess exits or is cancelled.
        Sets job status to "running" on start and "done"/"failed" on finish.
        """
        # Build popen kwargs.
        kwargs: dict = {  # type: ignore[type-arg]
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }
        if _is_posix():
            kwargs["start_new_session"] = True

        try:
            proc = subprocess.Popen(cmd, **kwargs)  # type: ignore[call-overload]
        except Exception as exc:
            self._jm.append_output(self._job_id, stderr=f"[ProcessGroupRunner] failed to start: {exc}\n")
            self._jm.finish(self._job_id, success=False)
            return -1

        with self._lock:
            self._proc = proc

        # Record PID/PGID.
        pgid = 0
        if _is_posix():
            try:
                pgid = os.getpgid(proc.pid)
            except Exception:
                pgid = proc.pid
        self._jm.set_pid(self._job_id, pid=proc.pid, pgid=pgid)
        self._jm.update_status(self._job_id, "running")

        # Stream output in background threads.
        def _drain(stream, key: str) -> None:
            for raw_line in stream:
                try:
                    line = raw_line.decode("utf-8", errors="replace")
                except Exception:
                    line = repr(raw_line)
                if key == "stdout":
                    self._jm.append_output(self._job_id, stdout=line, max_tail=self._tail_limit)
                else:
                    self._jm.append_output(self._job_id, stderr=line, max_tail=self._tail_limit)

        t_out = threading.Thread(target=_drain, args=(proc.stdout, "stdout"), daemon=True)
        t_err = threading.Thread(target=_drain, args=(proc.stderr, "stderr"), daemon=True)
        t_out.start()
        t_err.start()

        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._terminate_proc(proc, pgid)
            rc = proc.wait()
        finally:
            t_out.join(timeout=2)
            t_err.join(timeout=2)
            try:
                if proc.stdout:
                    proc.stdout.close()
                if proc.stderr:
                    proc.stderr.close()
            except Exception:
                pass

        with self._lock:
            self._proc = None

        self._jm.finish(self._job_id, success=(rc == 0))
        return rc

    def cancel(self, graceful_timeout: int = _GRACEFUL_TIMEOUT) -> None:
        """Signal the running process to stop.

        On POSIX: sends SIGTERM to the entire process group, then SIGKILL
        after *graceful_timeout* seconds if the process has not exited.
        On Windows: calls ``Popen.terminate()`` then ``Popen.kill()``.
        """
        self._jm.cancel(self._job_id)
        with self._lock:
            proc = self._proc
        if proc is None:
            return
        pgid = 0
        if _is_posix():
            try:
                pgid = os.getpgid(proc.pid)
            except Exception:
                pass
        self._terminate_proc(proc, pgid, graceful_timeout=graceful_timeout)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _terminate_proc(
        self,
        proc: subprocess.Popen,  # type: ignore[type-arg]
        pgid: int,
        graceful_timeout: int = _GRACEFUL_TIMEOUT,
    ) -> None:
        """Send SIGTERM (or terminate), then SIGKILL (or kill) after timeout."""
        if _is_posix() and pgid > 0:
            try:
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                return
            except Exception:
                pass
            deadline = time.time() + graceful_timeout
            while time.time() < deadline:
                if proc.poll() is not None:
                    return
                time.sleep(0.1)
            try:
                os.killpg(pgid, signal.SIGKILL)
            except Exception:
                pass
        else:
            # Windows fallback.
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=graceful_timeout)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except Exception:
                    pass
