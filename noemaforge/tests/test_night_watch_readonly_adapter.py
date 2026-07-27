#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_night_watch_readonly_adapter.py
Zone: release/package
Version: 0.33.0
Created: 2026-07-27
Modified: 2026-07-27
Purpose: Prove canonical, deterministic and non-mutating night_watch observation.
Inputs: Temporary synthetic night_watch state roots.
Outputs: unittest assertions only.
Side effects: Temporary-directory fixtures only.
Tests: direct unittest or pytest execution.
Notes: UAT request findings resolution.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict


ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

from evolution_adapters import night_watch_readonly as adapter


FULL_HEAD = "a" * 40


def tree_fingerprint(root: Path) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            result[relative] = f"symlink:{os.readlink(path)}"
        elif path.is_file():
            result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


class NightWatchReadOnlyAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.state = self.base / "state"
        (self.state / "work-items-v51").mkdir(parents=True)
        (self.state / "scheduler").mkdir()
        (self.state / "logs").mkdir()
        (self.state / "status.md").write_text(
            "\n".join(
                [
                    "- timestamp: 2026-07-27T12:00:00Z",
                    f"- head: {FULL_HEAD}",
                    "- stage: running-review",
                    "- active_agent: reviewer",
                    "- cycle: 7",
                    "- manual_pending: 1",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (self.state / "coordinator-lock-v51.json").write_text(
            json.dumps(
                {
                    "repo": "Sinev-Maksim/NoemaForge",
                    "base": "release/0.33.0-dev",
                    "started_at": "2026-07-27T11:55:00Z",
                    "head": FULL_HEAD,
                }
            ),
            encoding="utf-8",
        )
        (self.state / "work-items-v51/issue-12.json").write_text(
            json.dumps(
                {
                    "issue": 12,
                    "pr": 31,
                    "phase": "running",
                    "reason": "untrusted source text is data only",
                }
            ),
            encoding="utf-8",
        )
        (self.state / "scheduler/pr-31.json").write_text(
            json.dumps(
                {
                    "pr": 31,
                    "last_seen_head": FULL_HEAD,
                    "history_trusted": True,
                    "broad_review_done": False,
                }
            ),
            encoding="utf-8",
        )
        (self.state / "scheduler/pr-44.json").write_text(
            json.dumps(
                {
                    "pr": 44,
                    "last_seen_head": FULL_HEAD,
                    "history_trusted": False,
                    "broad_review_done": False,
                }
            ),
            encoding="utf-8",
        )
        (self.state / "logs/coordinator.log").write_text(
            "bounded observation fixture\n",
            encoding="utf-8",
        )

    def test_projection_uses_only_canonical_execution_contracts(self) -> None:
        snapshot = adapter.snapshot(self.state)
        self.assertTrue(
            snapshot["canonical_validation"]["ok"],
            snapshot["canonical_validation"]["failures"],
        )
        self.assertEqual(
            adapter.CANONICAL_API_VERSION,
            snapshot["evolution_run"]["apiVersion"],
        )
        self.assertTrue(snapshot["evolution_run"]["runtime_neutral"])
        self.assertTrue(
            {
                item["status"] for item in snapshot["work_items"]
            }.issubset({"planned", "ready", "blocked", "completed", "failed"})
        )
        self.assertEqual(
            [item["work_item_id"] for item in snapshot["work_items"]],
            snapshot["evolution_run"]["work_items"],
        )
        self.assertNotIn(
            "night-watch:pr:31",
            snapshot["evolution_run"]["work_items"],
        )

    def test_snapshot_is_byte_stable_for_unchanged_state(self) -> None:
        first = adapter.snapshot(self.state)
        second = adapter.snapshot(self.state)
        self.assertEqual(first, second)
        self.assertEqual(
            adapter.stable_hash(first),
            adapter.stable_hash(second),
        )

    def test_adapter_has_no_mutating_surface(self) -> None:
        snapshot = adapter.snapshot(self.state)
        self.assertEqual([], snapshot["mutating_operations"])
        self.assertEqual(
            ["probe", "snapshot", "artifacts", "blockers"],
            snapshot["operations"],
        )
        for item in snapshot["work_items"]:
            self.assertEqual(
                ["observe", "inspect_evidence"],
                item["allowed_actions"],
            )
            self.assertIn("commit", item["forbidden_actions"])
            self.assertIn("push", item["forbidden_actions"])
            self.assertIn("merge", item["forbidden_actions"])

    def test_snapshot_does_not_write_observed_state(self) -> None:
        before = tree_fingerprint(self.state)
        adapter.snapshot(self.state)
        after = tree_fingerprint(self.state)
        self.assertEqual(before, after)

    def test_short_head_is_explicitly_unknown(self) -> None:
        status = self.state / "status.md"
        status.write_text(
            "- timestamp: 2026-07-27T12:00:00Z\n"
            "- head: abc1234\n"
            "- stage: ready\n",
            encoding="utf-8",
        )
        snapshot = adapter.snapshot(self.state)
        self.assertIsNone(snapshot["source_observations"]["exact_head"])
        self.assertIn(
            "observed_head_not_full_sha",
            snapshot["warnings"],
        )

    def test_symlink_escape_is_rejected(self) -> None:
        outside = self.base / "outside.log"
        outside.write_text("secret\n", encoding="utf-8")
        link = self.state / "logs/escape.log"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        result = adapter.artifacts(self.state)
        paths = {item["relative_path"] for item in result["artifacts"]}
        self.assertNotIn("logs/escape.log", paths)
        self.assertIn("logs/escape.log:path_escape", result["warnings"])

    def test_oversized_file_is_rejected(self) -> None:
        oversized = self.state / "logs/oversized.log"
        with oversized.open("wb") as handle:
            handle.truncate(adapter.MAX_FILE_BYTES + 1)
        result = adapter.artifacts(self.state)
        paths = {item["relative_path"] for item in result["artifacts"]}
        self.assertNotIn("logs/oversized.log", paths)
        self.assertIn("logs/oversized.log:oversized", result["warnings"])

    def test_probe_reports_layout_ambiguity_without_combining_roots(self) -> None:
        home = self.base / "home"
        v46 = home / ".local/share/noemaforge-agent-runs/token-aware-0330-v46"
        v3 = home / ".local/share/noemaforge-agent-runs/token-aware-0330-v3"
        v46.mkdir(parents=True)
        v3.mkdir(parents=True)
        (v46 / "status.md").write_text("- stage: ready\n", encoding="utf-8")
        (v3 / "status.md").write_text("- stage: ready\n", encoding="utf-8")
        result = adapter.probe(environ={"HOME": str(home)}, home=home)
        self.assertTrue(result["available"])
        self.assertIn(
            "multiple_night_watch_state_roots_detected",
            result["warnings"],
        )
        self.assertIn(
            "v46_and_v3_state_layouts_both_present",
            result["warnings"],
        )

    def test_missing_usage_is_none_not_zero(self) -> None:
        (self.state / "status.md").write_text(
            "- timestamp: 2026-07-27T12:00:00Z\n"
            "- stage: planned\n",
            encoding="utf-8",
        )
        snapshot = adapter.snapshot(self.state)
        self.assertIsNone(snapshot["resource_usage"]["cycle"])
        self.assertIsNone(snapshot["resource_usage"]["token_usage"])
        self.assertIsNone(snapshot["resource_usage"]["cpu_usage"])
        self.assertIsNone(snapshot["resource_usage"]["ram_usage"])
        self.assertIsNone(snapshot["resource_usage"]["vram_usage"])


if __name__ == "__main__":
    unittest.main()
