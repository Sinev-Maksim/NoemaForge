#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_firstboot_attempt_archive_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate automatic archival of failed, interrupted and invalid firstboot attempts.
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


class FirstbootAttemptArchiveRuntimeTests(unittest.TestCase):
    def test_mark_started_archives_blocked_attempt_and_resets_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = root / "firstboot-status.json"
            events = root / "firstboot-events.jsonl"
            (root / "dataset-assurance.json").write_text('{"ok": false}\n', encoding="utf-8")

            firstboot_status.mark_started(str(status), str(events), share_root="/share", vault_root="/vault")
            firstboot_status.mark_finished(
                str(status),
                str(events),
                state="blocked_dataset_assurance",
                message="blocked",
                extra={"dataset_assurance": str(root / "dataset-assurance.json")},
            )

            firstboot_status.mark_started(str(status), str(events), share_root="/share2", vault_root="/vault2")

            current = json.loads(status.read_text(encoding="utf-8"))
            self.assertEqual("running", current["state"])
            archive = current["previous_attempt_archive"]
            self.assertEqual("failed_state_blocked_dataset_assurance", archive["reason"])
            archive_dir = Path(archive["archive_dir"])
            self.assertTrue((archive_dir / "firstboot-status.json").is_file())
            self.assertTrue((archive_dir / "firstboot-events.jsonl").is_file())
            self.assertTrue((archive_dir / "dataset-assurance.json").is_file())
            manifest = json.loads((archive_dir / "archive-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("blocked_dataset_assurance", manifest["state"])
            self.assertIn("dataset-assurance.json", manifest["copied_files"])

            lines = [line for line in events.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(1, len(lines))
            start_event = json.loads(lines[0])
            self.assertEqual("start", start_event["step"])
            self.assertIn("previous_attempt_archive", start_event["extra"])

    def test_invalid_status_is_archived_before_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = root / "firstboot-status.json"
            events = root / "firstboot-events.jsonl"
            status.write_text("{not-json", encoding="utf-8")
            events.write_text('{"step":"start","state":"running"}\n', encoding="utf-8")

            firstboot_status.mark_started(str(status), str(events), share_root="/share", vault_root="/vault")

            current = json.loads(status.read_text(encoding="utf-8"))
            archive = current["previous_attempt_archive"]
            self.assertEqual("status_invalid_json", archive["reason"])
            self.assertTrue(Path(archive["manifest"]).is_file())

    def test_successful_terminal_attempt_is_not_archived(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = root / "firstboot-status.json"
            events = root / "firstboot-events.jsonl"
            firstboot_status.mark_started(str(status), str(events), share_root="/share", vault_root="/vault")
            firstboot_status.mark_finished(str(status), str(events), state="selection_ready_no_apply", message="dry run")
            firstboot_status.mark_started(str(status), str(events), share_root="/share", vault_root="/vault")

            current = json.loads(status.read_text(encoding="utf-8"))
            self.assertNotIn("previous_attempt_archive", current)
            self.assertFalse((root / "firstboot-attempt-archive").exists())


if __name__ == "__main__":
    unittest.main()
