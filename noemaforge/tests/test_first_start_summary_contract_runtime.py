#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_first_start_summary_contract_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate first-start summary grouped-run and marker invariants.
Inputs: Workspace first-start summary policy and mocked summary fixtures.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import first_start_summary as fss
import first_start_summary_contract_runtime as fsscr
import production_ai_contracts as pac


class FirstStartSummaryContractRuntimeTests(unittest.TestCase):
    def test_workspace_first_start_summary_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "first-start-summary-policy.json"
        report = fsscr.validate_first_start_summary_policy(
            fsscr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["examples"])
        self.assertEqual(1, report["metrics"]["passing_examples"])
        self.assertEqual(3, report["metrics"]["runs"])
        self.assertEqual(9, report["metrics"]["events"])
        self.assertEqual(3, report["metrics"]["markers_seen"])

        gate = pac.evaluate_gate(
            {"change_id": "first-start-summary-output-core", "domain": "pipeline"},
            fsscr.first_start_summary_report_to_gate_evidence(report, artifact_uri="reports/first-start-summary.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_cli_output_groups_all_runs_and_uses_pass_warn_fail_markers(self) -> None:
        example = fsscr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "first_start_summary.example.json")

        def fake_json(path: Path, default):
            name = path.name
            if name == "firstboot-staffing-summary.json":
                return example["staffing"]
            if name == "firstboot-status.json":
                return example["status"]
            if name == "model-selection-decision.json":
                return example["decision"]
            return default

        stream = io.StringIO()
        with patch.object(fss, "load_events", return_value=example["events"]), patch.object(fss, "load_json", side_effect=fake_json):
            with redirect_stdout(stream):
                code = fss.main(["--bootstrap", "unused", "--all", "--no-color"])

        text = stream.getvalue()
        self.assertEqual(0, code)
        self.assertIn("Runs", text)
        self.assertIn("run=run-pass", text)
        self.assertIn("run=run-warn", text)
        self.assertIn("run=run-fail", text)
        self.assertIn("[PASS]", text)
        self.assertIn("[WARN]", text)
        self.assertIn("[FAIL]", text)
        self.assertIn("Timeline", text)
        self.assertIn("Staffing", text)
        self.assertIn("Final", text)

    def test_missing_start_boundary_breaks_run_grouping_contract(self) -> None:
        policy_path = ROOT / "configs" / "first-start-summary-policy.json"
        policy = fsscr.load_policy(policy_path)
        example = fsscr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "first_start_summary.example.json")
        broken = copy.deepcopy(example)
        broken["events"] = [event for event in broken["events"] if event.get("extra", {}).get("run_id") != "run-warn"]

        with patch.object(fsscr, "load_example_set", return_value=broken):
            report = fsscr.validate_first_start_summary_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("example_runs_too_few:2", report["failures"])

    def test_state_marker_map_must_match_runtime_mapping(self) -> None:
        policy_path = ROOT / "configs" / "first-start-summary-policy.json"
        policy = fsscr.load_policy(policy_path)
        policy["policy"]["state_marker_map"]["blocked_no_models"] = "WARN"

        report = fsscr.validate_first_start_summary_policy(
            policy,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("policy_state_marker_mismatch:blocked_no_models:WARN:FAIL", report["failures"])


if __name__ == "__main__":
    unittest.main()
