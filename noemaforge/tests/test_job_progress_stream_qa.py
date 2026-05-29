#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_job_progress_stream_qa.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test job progress stream registry and documentation coverage.
Inputs: Unified Registry, job progress stream policy and canonical documentation.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import job_progress_stream_runtime as jpsr
import unified_registry_runtime as urr

CLOSURE = "Closed by `job-progress-stream-core`"
TODO_ITEM = "Add streaming job progress SSE/WebSocket after alpha."


class JobProgressStreamQATests(unittest.TestCase):
    def test_pack_is_registered_with_gui_refs(self) -> None:
        registry_path = ROOT / "configs" / "unified-registry.json"
        report = urr.validate_unified_registry(
            urr.load_registry(registry_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=registry_path,
        )
        self.assertTrue(report["ok"], report["failures"])

        entries = {
            f"{entry['kind']}:{entry['id']}:{entry['version']}": entry
            for entry in report["normalized_registry"]["entries"]
        }
        pack = entries.get("eval-pack:job-progress-stream-core:0.32.2")
        self.assertIsNotNone(pack)
        self.assertIn("configs/job-progress-stream-policy.json", pack["refs"])
        self.assertIn("contracts/job_progress_stream.schema.json", pack["refs"])
        self.assertIn("src/job_progress_stream_runtime.py", pack["refs"])
        self.assertIn("src/admin_gui_server.py", pack["refs"])
        self.assertIn("templates/pipeline-dashboard/app.js", pack["refs"])
        self.assertIn("tests/test_job_progress_stream_performance.py", pack["refs"])

    def test_docs_and_changelog_record_closed_streaming_item(self) -> None:
        policy = jpsr.load_policy(ROOT / "configs" / "job-progress-stream-policy.json")
        report = jpsr.validate_job_progress_stream_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertEqual(0, backlog.count(f"- [ ] {TODO_ITEM}"))
        self.assertGreaterEqual(backlog.count(f"- [x] {TODO_ITEM}"), 3)
        self.assertIn(CLOSURE, backlog)

        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("job-progress-stream-core", text, str(path))
            self.assertIn("/api/jobs/stream", text, str(path))
            self.assertIn(CLOSURE, text, str(path))


if __name__ == "__main__":
    unittest.main()

