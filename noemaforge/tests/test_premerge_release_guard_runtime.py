#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_premerge_release_guard_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate pre-merge release guard invariants.
Inputs: Workspace pre-merge release guard policy and synthetic self-test reports.
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

import premerge_release_guard_runtime as prgr
import production_ai_contracts as pac
import selftest_runtime as strt


def report(run_id: str, *, failed: bool = False, duration: float = 0.4, rss: int = 9000) -> dict:
    return {
        "apiVersion": "noemaforge/v1",
        "kind": "SelfTestReport",
        "version": "0.32.1",
        "run_id": run_id,
        "suite": "core",
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
            {"case_id": "cli_status_json", "module": "operator_cli", "tier": "smoke", "status": "pass", "metrics": {"duration_sec": 0.2, "max_rss_kib": 8000, "disk_write_bytes": 32}},
            {"case_id": "pipeline_validate", "module": "pipeline_runtime", "tier": "unit", "status": "fail" if failed else "pass", "metrics": {"duration_sec": duration, "max_rss_kib": rss, "disk_write_bytes": 32}},
        ],
    }


class PremergeReleaseGuardRuntimeTests(unittest.TestCase):
    def test_workspace_premerge_release_guard_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "premerge-release-guard-policy.json"
        validation = prgr.validate_premerge_release_guard_policy(
            prgr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(2, validation["metrics"]["scenarios"])
        self.assertEqual(2, validation["metrics"]["passing_scenarios"])

        gate = pac.evaluate_gate(
            {"change_id": "premerge-release-guard-core", "domain": "pipeline"},
            prgr.premerge_release_guard_report_to_gate_evidence(validation, artifact_uri="reports/premerge-release-guard.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_guard_allows_clean_candidate_and_blocks_failed_regression(self) -> None:
        telemetry = strt.load_policy(ROOT)
        guard_policy = prgr.load_policy(ROOT / "configs" / "premerge-release-guard-policy.json")
        allowed = strt.build_premerge_release_guard(report("base"), report("current"), telemetry, guard_policy)
        blocked = strt.build_premerge_release_guard(report("base"), report("current_failed", failed=True, duration=1.0), telemetry, guard_policy)

        self.assertTrue(allowed["ok"], allowed)
        self.assertEqual("allow", allowed["decision"])
        self.assertFalse(blocked["ok"], blocked)
        self.assertEqual("block", blocked["decision"])
        blocker_kinds = {item["kind"] for item in blocked["blockers"]}
        self.assertIn("current_summary_not_ok", blocker_kinds)
        self.assertIn("required_case_not_passing", blocker_kinds)
        self.assertIn("current_case_not_passing", blocker_kinds)
        self.assertIn("baseline_regression", blocker_kinds)

    def test_release_guard_command_writes_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            baseline = tmp / "baseline.json"
            current = tmp / "current.json"
            out = tmp / "premerge-release-guard.json"
            baseline.write_text(json.dumps(report("base")), encoding="utf-8")
            current.write_text(json.dumps(report("current")), encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                strt.main(["--root", str(ROOT), "release-guard", "--baseline", str(baseline), "--current", str(current), "--out", str(out), "--json"])
            decision = json.loads(stdout.getvalue())
            self.assertTrue(decision["ok"], decision)
            self.assertTrue(out.exists())
            self.assertEqual("allow", json.loads(out.read_text(encoding="utf-8"))["decision"])

    def test_missing_required_case_breaks_guard(self) -> None:
        telemetry = strt.load_policy(ROOT)
        guard_policy = prgr.load_policy(ROOT / "configs" / "premerge-release-guard-policy.json")
        current = report("current")
        current["results"] = [current["results"][0]]
        decision = strt.build_premerge_release_guard(report("base"), current, telemetry, guard_policy)
        self.assertFalse(decision["ok"], decision)
        self.assertIn("required_case_missing", {item["kind"] for item in decision["blockers"]})


if __name__ == "__main__":
    unittest.main()
