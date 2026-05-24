#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_failure_forensics_bundle_readiness_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the failure forensics bundle readiness contract.
Inputs: Failure forensics bundle readiness policy and runtime validator.
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

import failure_forensics_bundle_readiness_runtime as ffbr


class FailureForensicsBundleReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_forensics(self) -> None:
        report = ffbr.validate_failure_forensics_bundle_readiness_policy(ffbr.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["failure_forensics_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["target_machine_required"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertGreaterEqual(summary["target_command_count"], 10)
        self.assertIn("forensics_bundle_path", report["evidence_requirements"])
        self.assertIn("redaction_manifest", report["evidence_requirements"])

    def test_forensics_capture_requires_operator_approval(self) -> None:
        payload = ffbr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "forensics-command-capture":
                check["requires_operator_approval"] = False
        failures = ffbr._policy_failures(broken)
        self.assertIn("check_operator_approval_required:forensics-command-capture", failures)

    def test_remote_upload_path_is_rejected(self) -> None:
        payload = ffbr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "forensics-command-capture":
                check["commands"].append("sudo noemaforge forensics --upload")
        failures = ffbr._policy_failures(broken)
        self.assertIn("check_forbidden_remote_or_mutating_token:forensics-command-capture:--upload", failures)

    def test_gate_evidence_report_is_bounded_and_explicit(self) -> None:
        report = ffbr.validate_failure_forensics_bundle_readiness_policy(ffbr.load_policy())
        evidence = ffbr.gate_evidence(
            report,
            artifact_uri="reports/failure-forensics-bundle-readiness.json",
        )
        self.assertEqual("failure_forensics_bundle_readiness", evidence["gate"])
        self.assertEqual("passed", evidence["status"])
        self.assertEqual(report["metrics"], evidence["metrics"])


if __name__ == "__main__":
    unittest.main()
