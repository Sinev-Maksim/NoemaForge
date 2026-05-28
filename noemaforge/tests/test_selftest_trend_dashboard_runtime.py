#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_selftest_trend_dashboard_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate self-test trend dashboard invariants.
Inputs: Workspace self-test trend dashboard policy and synthetic self-test reports.
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
import selftest_runtime as strt
import selftest_trend_dashboard_runtime as stdr


def report(run_id: str, *, failed: bool = False, duration: float = 0.5, rss: int = 10000) -> dict:
    return {
        "apiVersion": "noemaforge/v1",
        "kind": "SelfTestReport",
        "version": "0.32.1",
        "run_id": run_id,
        "suite": "core",
        "started_at": f"2026-05-20T0{run_id[-1]}:00:00Z",
        "finished_at": f"2026-05-20T0{run_id[-1]}:00:10Z",
        "summary": {
            "ok": not failed,
            "case_count": 2,
            "passed": 1 if failed else 2,
            "failed": 1 if failed else 0,
            "duration_total_sec": duration + 0.2,
            "duration_max_sec": duration,
            "max_rss_kib": rss,
            "disk_write_bytes_total": 64,
            "ecc_delta_total": 0,
        },
        "results": [
            {"case_id": "cli_status_json", "module": "operator_cli", "tier": "smoke", "status": "pass", "metrics": {"duration_sec": 0.2, "max_rss_kib": 9000, "disk_write_bytes": 32}},
            {"case_id": "pipeline_validate", "module": "pipeline_runtime", "tier": "unit", "status": "fail" if failed else "pass", "metrics": {"duration_sec": duration, "max_rss_kib": rss, "disk_write_bytes": 32}},
        ],
    }


class SelfTestTrendDashboardRuntimeTests(unittest.TestCase):
    def test_workspace_selftest_trend_dashboard_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "selftest-trend-dashboard-policy.json"
        validation = stdr.validate_selftest_trend_dashboard_policy(
            stdr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])

        gate = pac.evaluate_gate(
            {"change_id": "selftest-trend-dashboard-core", "domain": "pipeline"},
            stdr.selftest_trend_dashboard_report_to_gate_evidence(validation, artifact_uri="reports/selftest-trend-dashboard.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_trend_builder_detects_status_duration_and_rss_regression(self) -> None:
        dashboard = strt.build_trend_dashboard([
            report("run1", failed=False, duration=0.5, rss=10000),
            report("run2", failed=True, duration=1.0, rss=17000),
        ])

        self.assertEqual(2, dashboard["run_count"])
        self.assertEqual(2, dashboard["case_count"])
        warning_kinds = {item["kind"] for item in dashboard["warnings"]}
        self.assertIn("case_status_regression", warning_kinds)
        self.assertIn("case_duration_spike", warning_kinds)
        self.assertIn("case_rss_spike", warning_kinds)
        self.assertIn("failed_count_increase", warning_kinds)

    def test_trend_command_writes_json_and_html_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            first = tmp / "first.json"
            second = tmp / "second.json"
            first.write_text(json.dumps(report("run1")), encoding="utf-8")
            second.write_text(json.dumps(report("run2", failed=True)), encoding="utf-8")
            out_dir = tmp / "dashboard"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                strt.main(["--state", str(tmp / "state"), "trend", "--report", str(first), "--report", str(second), "--out-dir", str(out_dir), "--format", "json"])
            data = json.loads(stdout.getvalue())
            self.assertEqual(2, data["run_count"])
            self.assertTrue((out_dir / "selftest-trend.json").exists())
            html = (out_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn("self-test trend", html)
            self.assertIn("selftest-trend-data", html)

    def test_missing_expected_html_output_breaks_contract(self) -> None:
        policy = stdr.load_policy(ROOT / "configs" / "selftest-trend-dashboard-policy.json")
        example = stdr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "selftest_trend_dashboard.example.json")
        example["scenarios"][0]["expected_outputs"] = ["selftest-trend.json"]
        original = stdr.load_example_set
        try:
            stdr.load_example_set = lambda _path: example  # type: ignore[assignment]
            validation = stdr.validate_selftest_trend_dashboard_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        finally:
            stdr.load_example_set = original  # type: ignore[assignment]
        self.assertFalse(validation["ok"])
        self.assertIn("scenario:offline-two-run-regression-trend:scenario_expected_output_missing:index.html", validation["failures"])


if __name__ == "__main__":
    unittest.main()
