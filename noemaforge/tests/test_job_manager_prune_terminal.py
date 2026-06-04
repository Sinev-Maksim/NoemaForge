#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_job_manager_prune_terminal.py
Zone: release/package
Version: 0.32.2
Created: 2026-06-04
Modified: 2026-06-04
Purpose: Validate JobManager.prune_terminal age-based cleanup of the job index.
Inputs: job_manager module API.
Outputs: unittest assertions only.
Side effects: Creates and removes a temporary jobs directory.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import job_manager as jm


def _z(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class PruneTerminalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="nf-jobs-")
        self.dir = Path(self.tmp)
        self.mgr = jm.JobManager(self.dir)
        self.now = datetime.now(timezone.utc)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed(self, jobs) -> None:
        """jobs: iterable of (job_id, status, timestamp_iso) written to index + per-job files."""
        records = []
        for jid, status, ts in jobs:
            rec = {"job_id": jid, "kind": "test", "status": status,
                   "created_at": ts, "updated_at": ts, "finished_at": ts}
            records.append(rec)
            (self.dir / f"{jid}.json").write_text(json.dumps(rec), encoding="utf-8")
        (self.dir / "jobs.json").write_text(json.dumps({"jobs": records}), encoding="utf-8")

    def _index_ids(self):
        data = json.loads((self.dir / "jobs.json").read_text(encoding="utf-8"))
        return {j["job_id"] for j in data.get("jobs", [])}

    def test_prunes_old_terminal_keeps_recent_and_active(self) -> None:
        old = _z(self.now - timedelta(days=2))
        recent = _z(self.now - timedelta(seconds=60))
        self._seed([
            ("old_done", "done", old),
            ("old_failed", "failed", old),
            ("old_cancelled", "cancelled", old),
            ("recent_done", "done", recent),
            ("old_running", "running", old),       # active: never pruned
            ("old_queued", "queued", old),         # active: never pruned
        ])
        pruned = self.mgr.prune_terminal(max_age_seconds=86400)
        self.assertEqual({"old_done", "old_failed", "old_cancelled"}, set(pruned))
        self.assertEqual({"recent_done", "old_running", "old_queued"}, self._index_ids())

    def test_removes_per_job_file(self) -> None:
        self._seed([("old_done", "done", _z(self.now - timedelta(days=2)))])
        self.assertTrue((self.dir / "old_done.json").exists())
        self.mgr.prune_terminal(max_age_seconds=86400)
        self.assertFalse((self.dir / "old_done.json").exists())

    def test_active_never_pruned_regardless_of_age(self) -> None:
        ancient = _z(self.now - timedelta(days=400))
        self._seed([("a", "running", ancient), ("b", "needs_privilege", ancient)])
        self.assertEqual([], self.mgr.prune_terminal(max_age_seconds=1))
        self.assertEqual({"a", "b"}, self._index_ids())

    def test_terminal_with_unparseable_timestamp_is_kept(self) -> None:
        # All timestamps empty -> age unknown -> conservatively kept.
        self._seed([("no_ts", "done", "")])
        self.assertEqual([], self.mgr.prune_terminal(max_age_seconds=0))
        self.assertEqual({"no_ts"}, self._index_ids())

    def test_falls_back_to_created_at_when_finished_at_missing(self) -> None:
        old = _z(self.now - timedelta(days=2))
        rec = {"job_id": "j", "kind": "test", "status": "done",
               "created_at": old, "updated_at": old, "finished_at": ""}
        (self.dir / "j.json").write_text(json.dumps(rec), encoding="utf-8")
        (self.dir / "jobs.json").write_text(json.dumps({"jobs": [rec]}), encoding="utf-8")
        self.assertEqual(["j"], self.mgr.prune_terminal(max_age_seconds=86400))

    def test_corrupt_finished_at_falls_back_to_valid_created_at(self) -> None:
        # A non-empty but unparseable finished_at must not block the valid created_at.
        old = _z(self.now - timedelta(days=2))
        rec = {"job_id": "j", "kind": "test", "status": "done",
               "created_at": old, "updated_at": old, "finished_at": "not-a-timestamp"}
        (self.dir / "j.json").write_text(json.dumps(rec), encoding="utf-8")
        (self.dir / "jobs.json").write_text(json.dumps({"jobs": [rec]}), encoding="utf-8")
        self.assertEqual(["j"], self.mgr.prune_terminal(max_age_seconds=86400))

    def test_negative_max_age_is_noop(self) -> None:
        self._seed([("old_done", "done", _z(self.now - timedelta(days=2)))])
        self.assertEqual([], self.mgr.prune_terminal(max_age_seconds=-1))
        self.assertEqual({"old_done"}, self._index_ids())

    def test_empty_registry_returns_empty(self) -> None:
        self.assertEqual([], self.mgr.prune_terminal())

    def test_default_max_age_is_one_day(self) -> None:
        self._seed([
            ("eleven_h", "done", _z(self.now - timedelta(hours=11))),
            ("two_days", "done", _z(self.now - timedelta(days=2))),
        ])
        pruned = self.mgr.prune_terminal()  # default 86400s = 24h
        self.assertEqual(["two_days"], pruned)
        self.assertEqual({"eleven_h"}, self._index_ids())

    def test_traversal_job_id_does_not_delete_outside_jobs_dir(self) -> None:
        # A crafted job_id with path separators must NOT delete files outside jobs_dir.
        sentinel = self.dir.parent / "nf-prune-sentinel.json"
        sentinel.write_text("keep", encoding="utf-8")
        try:
            old = _z(self.now - timedelta(days=2))
            rec = {"job_id": "../nf-prune-sentinel", "kind": "test", "status": "done",
                   "created_at": old, "updated_at": old, "finished_at": old}
            (self.dir / "jobs.json").write_text(json.dumps({"jobs": [rec]}), encoding="utf-8")
            pruned = self.mgr.prune_terminal(max_age_seconds=86400)
            self.assertEqual(["../nf-prune-sentinel"], pruned)   # still removed from the index
            self.assertEqual(set(), self._index_ids())
            self.assertTrue(sentinel.exists(), "traversal job_id must not delete files outside jobs_dir")
        finally:
            sentinel.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
