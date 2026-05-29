#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_selftest_rss_slope_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate self-test RSS slope stress runner invariants.
Inputs: Workspace RSS slope policy and synthetic repeated self-test reports.
Outputs: unittest assertions only.
Side effects: Temporary files under unittest temp directories only.
Tests: direct unittest execution.
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

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import production_ai_contracts as pac
import selftest_rss_slope_runtime as rsr
import selftest_runtime as strt


def repeated_report(run_id: str = "rss_run") -> dict:
    return {
        "apiVersion": "noemaforge/v1",
        "kind": "SelfTestReport",
        "version": "0.32.1",
        "run_id": run_id,
        "suite": "stress",
        "started_at": "2026-05-20T03:11:00Z",
        "finished_at": "2026-05-20T03:11:12Z",
        "summary": {"ok": True, "case_count": 2, "passed": 2, "failed": 0, "duration_total_sec": 2.0, "duration_max_sec": 1.1, "max_rss_kib": 18000, "disk_write_bytes_total": 64, "ecc_delta_total": 0},
        "results": [
            {"case_id": "stable_case", "module": "synthetic", "tier": "stress", "status": "pass", "metrics": {"duration_sec": 0.5, "max_rss_kib": 8100}, "repeats": {"count": 4, "max_rss_kib_sequence": [8000, 8050, 8075, 8100], "memory_leak_suspect": False}},
            {"case_id": "leaky_case", "module": "synthetic", "tier": "stress", "status": "pass", "metrics": {"duration_sec": 0.6, "max_rss_kib": 18000}, "repeats": {"count": 4, "max_rss_kib_sequence": [10000, 12500, 15100, 18000], "memory_leak_suspect": True}},
        ],
    }


class SelfTestRssSlopeRuntimeTests(unittest.TestCase):
    def test_workspace_selftest_rss_slope_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "selftest-rss-slope-policy.json"
        validation = rsr.validate_selftest_rss_slope_policy(
            rsr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])

        gate = pac.evaluate_gate(
            {"change_id": "selftest-rss-slope-core", "domain": "pipeline"},
            rsr.selftest_rss_slope_report_to_gate_evidence(validation, artifact_uri="reports/selftest-rss-slope.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_rss_slope_builder_detects_repeat_growth(self) -> None:
        report = strt.build_rss_slope_report(repeated_report(), warn_slope_kib=512, fail_slope_kib=2048, min_repeats=3)
        by_case = {item["case_id"]: item for item in report["cases"]}

        self.assertFalse(report["ok"], report)
        self.assertEqual(2, report["summary"]["analyzed_cases"])
        self.assertEqual(1, report["summary"]["failures"])
        self.assertEqual("info", by_case["stable_case"]["severity"])
        self.assertEqual("fail", by_case["leaky_case"]["severity"])
        self.assertGreater(by_case["leaky_case"]["slope_kib_per_repeat"], 2500)

    def test_stress_command_writes_json_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            report_path = tmp / "selftest-report.json"
            out_path = tmp / "selftest-rss-slope.json"
            report_path.write_text(json.dumps(repeated_report("cli_rss")), encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                strt.main(["stress", "--report", str(report_path), "--out", str(out_path), "--json"])
            data = json.loads(stdout.getvalue())

            self.assertTrue(out_path.exists())
            self.assertEqual("SelfTestRssSlopeReport", data["kind"])
            self.assertEqual(data, json.loads(out_path.read_text(encoding="utf-8")))
            self.assertEqual(1, data["summary"]["failures"])

    def test_bad_expected_failure_count_breaks_contract(self) -> None:
        policy = rsr.load_policy(ROOT / "configs" / "selftest-rss-slope-policy.json")
        example = rsr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "selftest_rss_slope.example.json")
        example["scenarios"][0]["expected_failures"] = 2
        original = rsr.load_example_set
        try:
            rsr.load_example_set = lambda _path: example  # type: ignore[assignment]
            validation = rsr.validate_selftest_rss_slope_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        finally:
            rsr.load_example_set = original  # type: ignore[assignment]
        self.assertFalse(validation["ok"])
        self.assertIn("scenario:offline-repeat-rss-slope-finding:scenario_failures_mismatch:1", validation["failures"])


if __name__ == "__main__":
    unittest.main()
