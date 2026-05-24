#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_firstboot_attempt_archive_performance.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test synthetic failed firstboot archival.
Inputs: Temporary synthetic failed firstboot attempts.
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
import time
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import firstboot_status


class FirstbootAttemptArchivePerformanceTests(unittest.TestCase):
    def test_many_small_failed_attempts_archive_under_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_root = root / "archive"
            started = time.perf_counter()
            archived = 0
            for index in range(120):
                run_dir = root / f"run-{index:03d}"
                run_dir.mkdir()
                status = run_dir / "firstboot-status.json"
                events = run_dir / "firstboot-events.jsonl"
                status.write_text(json.dumps({
                    "apiVersion": "noemaforge.firstbootstatus/v1",
                    "kind": "FirstbootStatus",
                    "step": "complete",
                    "state": "blocked_no_role_candidates",
                    "run_id": f"run-{index:03d}",
                }), encoding="utf-8")
                events.write_text('{"step":"start","state":"running"}\n{"step":"complete","state":"blocked_no_role_candidates"}\n', encoding="utf-8")
                report = firstboot_status.archive_previous_attempt(
                    str(status),
                    str(events),
                    state_dir=str(run_dir),
                    archive_root=str(archive_root),
                )
                archived += int(bool(report.get("archived")))
            elapsed = time.perf_counter() - started

            self.assertEqual(120, archived)
            self.assertEqual(120, len([p for p in archive_root.iterdir() if p.is_dir()]))
            self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
