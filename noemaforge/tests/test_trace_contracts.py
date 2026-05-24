#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_trace_contracts.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-18
Modified: 2026-05-18
Purpose: Validate trace propagation for GUI-facing model-selection and pipeline control-plane runs.
Inputs: Temporary runtime state directories and explicit trace ids.
Outputs: unittest assertions only.
Side effects: Temporary files under unittest-managed temp directories.
Tests: unittest discovery.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import model_selection_runtime
import pipeline_runtime
import admin_runtime


class TraceContractTests(unittest.TestCase):
    def test_model_selection_plan_persists_trace_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "model-selection"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = model_selection_runtime.main([
                    "--root", str(ROOT),
                    "--state", str(state),
                    "plan",
                    "--request", "trace smoke",
                    "--trace-id", "trace-model-selection",
                    "--json",
                ])
            self.assertEqual(0, rc)
            result = json.loads(buf.getvalue())
            self.assertEqual("trace-model-selection", result["trace_id"])
            plan = json.loads(Path(result["artifacts"]["candidate_selection_plan"]).read_text(encoding="utf-8"))
            decision = json.loads(Path(result["artifacts"]["model_selection_decision"]).read_text(encoding="utf-8"))
            rollback = json.loads(Path(result["artifacts"]["rollback_plan"]).read_text(encoding="utf-8"))
            self.assertEqual("trace-model-selection", plan["trace_id"])
            self.assertEqual("trace-model-selection", decision["trace_id"])
            self.assertEqual("trace-model-selection", rollback["trace_id"])

    def test_pipeline_run_persists_trace_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "pipelines"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = pipeline_runtime.main([
                    "--root", str(ROOT),
                    "--state", str(state),
                    "run",
                    "public_mwp",
                    "--task-id", "trace",
                    "--request", "trace smoke",
                    "--trace-id", "trace-pipeline-run",
                ])
            self.assertEqual(0, rc)
            result = json.loads(buf.getvalue())
            self.assertEqual("trace-pipeline-run", result["trace_id"])
            manifest = json.loads((Path(result["run_dir"]) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("trace-pipeline-run", manifest["trace_id"])

    def test_admin_route_attaches_abstention_decision(self) -> None:
        greeting = admin_runtime.route_request("Привет")
        self.assertEqual("route", greeting["abstention"]["action"])

        code_without_context = admin_runtime.route_request("Доработай код")
        self.assertEqual("code", code_without_context["id"])
        self.assertEqual("ask_clarification", code_without_context["abstention"]["action"])
        self.assertIn("project path", code_without_context["missing_context"])


if __name__ == "__main__":
    unittest.main()
