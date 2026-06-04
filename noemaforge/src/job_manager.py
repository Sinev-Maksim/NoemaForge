#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/src/job_manager.py
Zone: runtime/orchestration
Version: 0.32.2
Created: 2026-05-27
Modified: 2026-05-27
Purpose: File-backed job tracking with PID/pgid, cancellation flag, stdout/stderr tails, and idempotency.
Inputs: jobs_dir path; callers supply kind, command, idempotency_key, lock_key.
Outputs: Normalized job records (dicts) persisted to <jobs_dir>/jobs.json and per-job JSON files.
Side effects: Reads/writes files under jobs_dir. Thread-safe via per-file updates.
Tests: python3 -m unittest noemaforge/tests/test_job_manager.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from noemaforge_version import RUNTIME_VERSION
from orchestration_state import ACTIVE_JOB_STATES, FINAL_JOB_STATES


def _nowz() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_z(value: str) -> Optional[float]:
    """Parse an ISO-8601 'Z'/offset timestamp to a POSIX timestamp; None if unparseable."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _new_job_id(kind: str) -> str:
    ts = _nowz().replace(":", "").replace("-", "").replace("Z", "")
    slug = kind.replace("-", "_")[:24]
    rand = uuid.uuid4().hex[:6]
    return f"job_{ts}_{slug}_{rand}"


def _empty_progress() -> Dict[str, Any]:
    return {"current": 0, "total": 0, "label": "queued"}


def _normalize(record: Dict[str, Any]) -> Dict[str, Any]:
    """Return a fully-populated, typed copy of a job record.

    Unknown/extra fields (e.g. ``privileged_runner_command``) are preserved
    so callers can freely annotate job dicts and round-trip them through
    persist/read without losing data.
    """
    progress = record.get("progress")
    if not isinstance(progress, dict):
        progress = _empty_progress()

    artifacts = record.get("artifacts")
    if not isinstance(artifacts, list):
        artifacts = []

    # Start with a full copy to preserve caller-supplied extra fields.
    out = dict(record)
    out.update({
        "job_id": str(record.get("job_id") or ""),
        "kind": str(record.get("kind") or "unknown"),
        "status": str(record.get("status") or "queued"),
        "lock_key": str(record.get("lock_key") or ""),
        "idempotency_key": str(record.get("idempotency_key") or ""),
        "pid": int(record.get("pid") or 0),
        "pgid": int(record.get("pgid") or 0),
        "cancellation_flag": bool(record.get("cancellation_flag")),
        "progress": progress,
        "artifacts": artifacts,
        "stdout_tail": str(record.get("stdout_tail") or ""),
        "stderr_tail": str(record.get("stderr_tail") or ""),
        "command": str(record.get("command") or ""),
        "trace_id": str(record.get("trace_id") or ""),
        "created_at": str(record.get("created_at") or _nowz()),
        "updated_at": str(record.get("updated_at") or _nowz()),
        "finished_at": str(record.get("finished_at") or ""),
        "last_heartbeat": str(record.get("last_heartbeat") or ""),
        "version": str(record.get("version") or RUNTIME_VERSION),
    })
    return out



class JobManager:
    """File-backed job registry with idempotency, PID tracking, and cancel support.

    Directory layout::

        <jobs_dir>/
            jobs.json          # master list: {"jobs": [...]}
            <job_id>.json      # per-job record (authoritative copy)

    All public methods return a copy of the (normalized) job record or None when
    the job does not exist.
    """

    def __init__(self, jobs_dir: Path) -> None:
        self._dir = Path(jobs_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._jobs_file = self._dir / "jobs.json"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_index(self) -> Dict[str, Any]:
        """Load jobs.json; return {"jobs": [...]} even if file is missing/corrupt."""
        if not self._jobs_file.exists():
            return {"jobs": []}
        try:
            data = json.loads(self._jobs_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "jobs" not in data:
                return {"jobs": []}
            return data
        except Exception:
            return {"jobs": []}

    def _write_index(self, data: Dict[str, Any]) -> None:
        self._write_json_atomic(self._jobs_file, data)

    def _read_job_file(self, job_id: str) -> Optional[Dict[str, Any]]:
        path = self._dir / f"{job_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _write_job_file(self, job: Dict[str, Any]) -> None:
        path = self._dir / f"{job['job_id']}.json"
        self._write_json_atomic(path, job)

    @staticmethod
    def _write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _save(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a job record to both the per-job file and the index."""
        job["updated_at"] = _nowz()
        self._write_job_file(job)
        # Update master index.
        data = self._read_index()
        jobs = data.setdefault("jobs", [])
        for i, existing in enumerate(jobs):
            if existing.get("job_id") == job["job_id"]:
                jobs[i] = job
                self._write_index(data)
                return dict(job)
        jobs.append(job)
        self._write_index(data)
        return dict(job)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(
        self,
        kind: str,
        *,
        idempotency_key: str = "",
        lock_key: str = "",
        command: str = "",
        progress: Optional[Dict[str, Any]] = None,
        artifacts: Optional[List[Dict[str, Any]]] = None,
        trace_id: str = "",
        status: str = "queued",
    ) -> Dict[str, Any]:
        """Create a new job, or return an existing active job for the same idempotency_key.

        If *idempotency_key* is non-empty and a job with that key already exists in an
        active state (queued / starting / running / cancel_requested), the existing job
        is returned unchanged.
        """
        if idempotency_key:
            data = self._read_index()
            for existing in data.get("jobs", []):
                if (
                    existing.get("idempotency_key") == idempotency_key
                    and existing.get("status") in ACTIVE_JOB_STATES
                ):
                    # Reload from per-job file for freshest data.
                    fresh = self._read_job_file(existing["job_id"])
                    return _normalize(fresh if fresh is not None else existing)

        job = _normalize(
            {
                "job_id": _new_job_id(kind),
                "kind": kind,
                "status": status or "queued",
                "lock_key": lock_key,
                "idempotency_key": idempotency_key,
                "pid": 0,
                "pgid": 0,
                "cancellation_flag": False,
                "progress": progress or _empty_progress(),
                "artifacts": artifacts or [],
                "stdout_tail": "",
                "stderr_tail": "",
                "command": command,
                "trace_id": trace_id,
                "created_at": _nowz(),
                "updated_at": _nowz(),
                "finished_at": "",
                "version": RUNTIME_VERSION,
            }
        )
        return self._save(job)

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Return the normalized job record, or None if not found."""
        raw = self._read_job_file(job_id)
        if raw is None:
            # Fallback: scan index.
            data = self._read_index()
            for j in data.get("jobs", []):
                if j.get("job_id") == job_id:
                    return _normalize(j)
            return None
        return _normalize(raw)

    def list_all(self) -> List[Dict[str, Any]]:
        """Return all jobs from the index, newest first by created_at."""
        data = self._read_index()
        jobs = [_normalize(j) for j in data.get("jobs", [])]
        return sorted(jobs, key=lambda j: j["created_at"], reverse=True)

    def list_active(self) -> List[Dict[str, Any]]:
        """Return only jobs in active states (queued / starting / running / cancel_requested)."""
        return [j for j in self.list_all() if j["status"] in ACTIVE_JOB_STATES]

    def prune_terminal(self, max_age_seconds: int = 86400) -> List[str]:
        """Remove terminal jobs (done / failed / cancelled) older than *max_age_seconds*.

        Age is measured from ``finished_at``, falling back to ``updated_at`` then
        ``created_at``. Active jobs are never pruned, and a terminal job whose
        timestamps are all missing or unparseable is kept (conservative). Both the
        index entry and the per-job ``<job_id>.json`` file are removed. Returns the
        list of pruned job_ids. This bounds unbounded growth of the job index.
        """
        if max_age_seconds < 0:
            return []
        cutoff = datetime.now(timezone.utc).timestamp() - max_age_seconds
        data = self._read_index()
        kept: List[Dict[str, Any]] = []
        pruned: List[str] = []
        for job in data.get("jobs", []):
            status = str(job.get("status") or "")
            ts = _parse_z(job.get("finished_at") or job.get("updated_at") or job.get("created_at") or "")
            if status in FINAL_JOB_STATES and ts is not None and ts < cutoff:
                job_id = str(job.get("job_id") or "")
                pruned.append(job_id)
                if job_id:
                    try:
                        (self._dir / f"{job_id}.json").unlink(missing_ok=True)
                    except OSError:
                        pass
            else:
                kept.append(job)
        if pruned:
            data["jobs"] = kept
            self._write_index(data)
        return pruned

    def update_status(
        self,
        job_id: str,
        status: str,
        *,
        progress: Optional[Dict[str, Any]] = None,
        artifacts: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update job status and optionally progress/artifacts."""
        job = self.get(job_id)
        if job is None:
            return None
        job["status"] = status
        if progress is not None:
            job["progress"] = progress
        if artifacts is not None:
            job["artifacts"] = artifacts
        return self._save(job)

    def set_pid(self, job_id: str, *, pid: int, pgid: int) -> Optional[Dict[str, Any]]:
        """Record the OS PID and process-group ID of the running job subprocess."""
        job = self.get(job_id)
        if job is None:
            return None
        job["pid"] = pid
        job["pgid"] = pgid
        return self._save(job)

    def cancel(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Request cancellation of an active job.

        Sets ``cancellation_flag = True`` and ``status = "cancel_requested"``.
        If the job is already in a final state, returns None (no-op).
        """
        job = self.get(job_id)
        if job is None:
            return None
        if job["status"] in FINAL_JOB_STATES:
            return None
        job["cancellation_flag"] = True
        job["status"] = "cancel_requested"
        return self._save(job)

    def append_output(
        self,
        job_id: str,
        *,
        stdout: str = "",
        stderr: str = "",
        max_tail: int = 2000,
    ) -> Optional[Dict[str, Any]]:
        """Append text to the stdout/stderr tail buffers, bounded to *max_tail* chars.

        When the buffer exceeds *max_tail*, the oldest bytes are truncated from
        the front so the tail always shows the most recent output.
        """
        job = self.get(job_id)
        if job is None:
            return None
        if stdout:
            combined = job["stdout_tail"] + stdout
            if len(combined) > max_tail:
                combined = combined[-max_tail:]
            job["stdout_tail"] = combined
        if stderr:
            combined = job["stderr_tail"] + stderr
            if len(combined) > max_tail:
                combined = combined[-max_tail:]
            job["stderr_tail"] = combined
        return self._save(job)

    def finish(
        self,
        job_id: str,
        *,
        success: bool,
        artifacts: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Mark a job as done or failed, recording a finished_at timestamp."""
        job = self.get(job_id)
        if job is None:
            return None
        job["status"] = "done" if success else "failed"
        job["finished_at"] = _nowz()
        if artifacts is not None:
            job["artifacts"] = artifacts
        return self._save(job)

    def heartbeat(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Record that the job process is still alive by updating ``last_heartbeat``.

        Call this periodically from the job subprocess or its watchdog thread.
        Returns the updated job record, or None if the job does not exist.
        """
        job = self.get(job_id)
        if job is None:
            return None
        job["last_heartbeat"] = _nowz()
        return self._save(job)

    def is_stale(self, job_id: str, *, stale_seconds: int = 120) -> bool:
        """Return True when the job has not sent a heartbeat within *stale_seconds*.

        A job with no ``last_heartbeat`` and whose ``updated_at`` is older than
        *stale_seconds* is considered stale.  Missing jobs are always stale.
        """
        job = self.get(job_id)
        if job is None:
            return True
        ts_str = str(job.get("last_heartbeat") or job.get("updated_at") or "")
        if not ts_str:
            return True
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            return age > stale_seconds
        except Exception:
            return True
