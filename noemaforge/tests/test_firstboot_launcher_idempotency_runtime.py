#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_firstboot_launcher_idempotency_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate firstboot launcher rerun/idempotency lease behavior.
Inputs: Temporary firstboot status/events fixtures.
Outputs: unittest assertions only.
Side effects: Temporary-directory file writes only.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import firstboot_status


class FirstbootLauncherIdempotencyRuntimeTests(unittest.TestCase):
    def test_active_run_lease_blocks_duplicate_launcher_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = root / "firstboot-status.json"
            events = root / "firstboot-events.jsonl"

            first = firstboot_status.acquire_run_lease(str(status), str(events))
            second = firstboot_status.acquire_run_lease(str(status), str(events))

            self.assertTrue(first["ok"], first)
            self.assertFalse(second["ok"], second)
            self.assertEqual("active_firstboot_run", second["reason"])
            self.assertEqual(os.getpid(), second["pid"])

    def test_mark_finished_releases_launcher_lease_for_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = root / "firstboot-status.json"
            events = root / "firstboot-events.jsonl"

            firstboot_status.acquire_run_lease(str(status), str(events))
            firstboot_status.mark_started(str(status), str(events), share_root="/share", vault_root="/vault")
            firstboot_status.mark_finished(str(status), str(events), state="selection_ready_no_apply", message="dry run")
            next_run = firstboot_status.acquire_run_lease(str(status), str(events))

            self.assertTrue(next_run["ok"], next_run)
            lease = json.loads((root / "firstboot-run.lock").read_text(encoding="utf-8"))
            self.assertEqual("running", lease["state"])
            self.assertEqual(os.getpid(), lease["pid"])

    def test_stale_running_lock_is_replaced_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = root / "firstboot-status.json"
            events = root / "firstboot-events.jsonl"
            lock = root / "firstboot-run.lock"
            lock.write_text(json.dumps({
                "apiVersion": "noemaforge.firstbootlease/v1",
                "kind": "FirstbootRunLease",
                "state": "running",
                "pid": -1,
                "started_at": "2026-05-20T00:00:00Z",
            }), encoding="utf-8")

            acquired = firstboot_status.acquire_run_lease(str(status), str(events))
            current = json.loads(lock.read_text(encoding="utf-8"))

            self.assertTrue(acquired["ok"], acquired)
            self.assertTrue(current["replaced_previous_lock"])
            self.assertEqual(os.getpid(), current["pid"])


if __name__ == "__main__":
    unittest.main()
