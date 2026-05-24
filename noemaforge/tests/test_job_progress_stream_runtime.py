#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_job_progress_stream_runtime.py
Zone: gui/control-plane
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Admin GUI job-progress SSE contract behavior.
Inputs: Job progress stream policy and synthetic jobs.
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

import admin_gui_server as ags
import job_progress_stream_runtime as jpsr
import production_ai_contracts as pac


class JobProgressStreamRuntimeTests(unittest.TestCase):
    def test_policy_validates_and_maps_to_gui_gate(self) -> None:
        policy = jpsr.load_policy(ROOT / "configs" / "job-progress-stream-policy.json")
        report = jpsr.validate_job_progress_stream_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertTrue(report["ok"], report["failures"])
        gate = pac.evaluate_gate(
            {
                "change_id": "job-progress-stream-core",
                "domain": "pipeline",
                "required_checks": ["pipeline_eval", "rollback_plan"],
            },
            {
                "artifact_uri": "reports/job-progress-stream.json",
                "run_at": "2026-05-20T00:00:00Z",
                "checks": [
                    {"id": "pipeline_eval", "status": "passed" if report["ok"] else "failed"},
                    {"id": "rollback_plan", "status": "passed"},
                ],
            },
        )
        self.assertTrue(gate["ok"], gate)

    def test_sse_format_contains_snapshot_and_progress_events(self) -> None:
        events = jpsr.build_job_stream_events([
            {"job_id": "job_demo", "kind": "demo", "status": "running", "progress": {"step": 1, "total": 3}},
        ])
        text = jpsr.format_sse_events(events)

        self.assertIn("retry: 3000", text)
        self.assertIn("event: jobs_snapshot", text)
        self.assertIn("event: job_progress", text)
        self.assertIn('"job_id": "job_demo"', text)

    def test_admin_gui_sse_event_helper_emits_event_stream_lines(self) -> None:
        text = ags.sse_event("job_progress", {"ok": True, "stream": "job_progress_sse"}, event_id="job_demo")

        self.assertIn("id: job_demo", text)
        self.assertIn("event: job_progress", text)
        self.assertIn("data: ", text)
        self.assertTrue(text.endswith("\n\n"))


if __name__ == "__main__":
    unittest.main()
