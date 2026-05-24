#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_trace_coverage_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate executable trace coverage checks for control-plane surfaces.
Inputs: Workspace source files plus temporary broken fixtures.
Outputs: unittest assertions only.
Side effects: Creates and removes temporary fixture directories.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import trace_coverage_runtime as tcr


class TraceCoverageRuntimeTests(unittest.TestCase):
    def test_workspace_trace_coverage_validates_required_surfaces(self) -> None:
        report = tcr.validate_trace_coverage(PROJECT_ROOT)

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(8, report["metrics"]["surface_total"])
        self.assertEqual(8, report["metrics"]["surface_passed"])
        self.assertEqual(0, report["metrics"]["surface_failed"])
        self.assertEqual(
            {
                "admin_gui_messages",
                "admin_gui_jobs",
                "admin_runtime",
                "model_selection",
                "pipeline_runs",
                "epoch_apply_release_evidence",
                "toolproxy_calls",
                "telemetry_tool_calls",
            },
            {row["id"] for row in report["surfaces"]},
        )

    def test_trace_coverage_blocks_missing_surface_needle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="trace-coverage-", dir=os.path.dirname(__file__)) as tmp:
            project = Path(tmp)
            surface_path = project / "noemaforge" / "src" / "sample.py"
            surface_path.parent.mkdir(parents=True, exist_ok=True)
            surface_path.write_text("trace_id = 'present'\n", encoding="utf-8")

            report = tcr.validate_trace_coverage(
                project,
                surfaces=[
                    {
                        "id": "sample",
                        "path": "noemaforge/src/sample.py",
                        "description": "broken fixture",
                        "needles": ["trace_id", "new_trace_id("],
                    }
                ],
            )

            self.assertFalse(report["ok"])
            self.assertEqual(["surface_trace_missing:sample"], report["failures"])
            self.assertEqual(["new_trace_id("], report["surfaces"][0]["missing_needles"])


if __name__ == "__main__":
    unittest.main()
