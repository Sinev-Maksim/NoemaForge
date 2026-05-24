#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_toolproxy_capability_live_smoke_readiness_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the ToolProxy capability live-smoke readiness contract.
Inputs: ToolProxy capability live-smoke readiness policy and runtime validator.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import toolproxy_capability_live_smoke_readiness_runtime as tcls


class ToolProxyCapabilityLiveSmokeReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_toolproxy(self) -> None:
        report = tcls.validate_toolproxy_capability_live_smoke_readiness_policy(tcls.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["toolproxy_capability_live_smoke_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["target_machine_required"])
        self.assertTrue(summary["operator_approval_required"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertGreaterEqual(summary["target_command_count"], 10)
        self.assertIn("capability_issue_json", report["evidence_requirements"])
        self.assertIn("capability_verify_json", report["evidence_requirements"])

    def test_issue_and_verify_live_checks_require_operator_approval(self) -> None:
        payload = tcls.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "capability-issue-live":
                check["requires_operator_approval"] = False
        failures = tcls._policy_failures(broken)
        self.assertIn("check_operator_approval_required:capability-issue-live", failures)

    def test_remote_upload_path_is_rejected(self) -> None:
        payload = tcls.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "live-smoke-archive":
                check["commands"].append("sudo noemaforge forensics --upload")
        failures = tcls._policy_failures(broken)
        self.assertIn("check_forbidden_token:live-smoke-archive:--upload", failures)

    def test_gate_evidence_report_is_bounded_and_explicit(self) -> None:
        report = tcls.validate_toolproxy_capability_live_smoke_readiness_policy(tcls.load_policy())
        evidence = tcls.gate_evidence(
            report,
            artifact_uri="reports/toolproxy-capability-live-smoke-readiness.json",
        )
        self.assertEqual("toolproxy_capability_live_smoke_readiness", evidence["gate"])
        self.assertEqual("passed", evidence["status"])
        self.assertEqual(report["metrics"], evidence["metrics"])


if __name__ == "__main__":
    unittest.main()
