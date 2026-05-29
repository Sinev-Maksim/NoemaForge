#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_selftest_event_store_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate self-test event store invariants.
Inputs: Workspace event-store policy and synthetic self-test reports.
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
import selftest_event_store_runtime as sesr
import selftest_runtime as strt


def report(run_id: str = "events_run", *, failed: bool = True) -> dict:
    return {
        "apiVersion": "noemaforge/v1",
        "kind": "SelfTestReport",
        "version": "0.32.1",
        "run_id": run_id,
        "suite": "core",
        "started_at": "2026-05-20T02:56:00Z",
        "finished_at": "2026-05-20T02:56:05Z",
        "summary": {
            "ok": not failed,
            "case_count": 2,
            "passed": 1 if failed else 2,
            "failed": 1 if failed else 0,
            "duration_total_sec": 1.0,
            "duration_max_sec": 0.7,
            "max_rss_kib": 12000,
            "disk_write_bytes_total": 64,
            "ecc_delta_total": 0,
        },
        "results": [
            {"case_id": "cli_status_json", "module": "operator_cli", "tier": "smoke", "status": "pass", "metrics": {"duration_sec": 0.3, "max_rss_kib": 8000, "disk_write_bytes": 32}},
            {"case_id": "pipeline_validate", "module": "pipeline_runtime", "tier": "unit", "status": "fail" if failed else "pass", "problems": ["stdout missing ok"] if failed else [], "metrics": {"duration_sec": 0.7, "max_rss_kib": 12000, "disk_write_bytes": 32}},
        ],
    }


class SelfTestEventStoreRuntimeTests(unittest.TestCase):
    def test_workspace_selftest_event_store_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "selftest-event-store-policy.json"
        validation = sesr.validate_selftest_event_store_policy(
            sesr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])

        gate = pac.evaluate_gate(
            {"change_id": "selftest-event-store-core", "domain": "pipeline"},
            sesr.selftest_event_store_report_to_gate_evidence(validation, artifact_uri="reports/selftest-event-store.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_report_records_deterministic_run_and_case_events(self) -> None:
        sample = report()
        built = strt.build_test_events_from_report(sample)
        rebuilt = strt.build_test_events_from_report(sample)
        self.assertEqual([item["event_id"] for item in built], [item["event_id"] for item in rebuilt])

        with tempfile.TemporaryDirectory() as raw:
            state = Path(raw) / "state"
            conn = strt.db_connect(state)
            try:
                events = strt.record_test_events_for_report(conn, sample)
            finally:
                conn.close()
            export = strt.export_test_events(state, run_id="events_run")

        self.assertEqual(3, len(events))
        self.assertEqual(3, export["event_count"])
        self.assertEqual({"selftest.run.summary", "selftest.case.result"}, {item["event_type"] for item in export["events"]})
        self.assertIn("error", {item["severity"] for item in export["events"]})

    def test_events_ingest_and_export_commands_round_trip_json(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            report_path = tmp / "report.json"
            state = tmp / "state"
            out_path = tmp / "events.json"
            report_path.write_text(json.dumps(report("cli_events")), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                strt.main(["--state", str(state), "events", "ingest", "--report", str(report_path), "--json"])
            ingest = json.loads(stdout.getvalue())
            self.assertEqual(3, ingest["event_count"])

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                strt.main(["--state", str(state), "events", "export", "--run-id", "cli_events", "--out", str(out_path), "--json"])
            export = json.loads(stdout.getvalue())

            self.assertTrue(out_path.exists())
            self.assertEqual(3, export["event_count"])
            self.assertEqual(export, json.loads(out_path.read_text(encoding="utf-8")))

    def test_bad_expected_event_count_breaks_contract(self) -> None:
        policy = sesr.load_policy(ROOT / "configs" / "selftest-event-store-policy.json")
        example = sesr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "selftest_event_store.example.json")
        example["scenarios"][0]["expected_event_count"] = 4
        original = sesr.load_example_set
        try:
            sesr.load_example_set = lambda _path: example  # type: ignore[assignment]
            validation = sesr.validate_selftest_event_store_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        finally:
            sesr.load_example_set = original  # type: ignore[assignment]
        self.assertFalse(validation["ok"])
        self.assertIn("scenario:offline-report-to-canonical-events:scenario_event_count_mismatch:3", validation["failures"])


if __name__ == "__main__":
    unittest.main()
