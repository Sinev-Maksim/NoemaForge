#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_trixie_preflight_target_readiness_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the Trixie preflight target readiness contract.
Inputs: Trixie preflight target readiness policy and runtime validator.
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

import trixie_preflight_target_readiness_runtime as tptr


class TrixiePreflightTargetReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_preflight(self) -> None:
        report = tptr.validate_trixie_preflight_target_readiness_policy(tptr.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["trixie_preflight_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["target_machine_required"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertGreaterEqual(summary["target_command_count"], 10)
        self.assertIn("trixie_preflight_json", report["evidence_requirements"])
        self.assertIn("missing_dependencies", report["evidence_requirements"])

    def test_primary_preflight_requires_operator_approval(self) -> None:
        payload = tptr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "preflight-command-baseline":
                check["requires_operator_approval"] = False
        failures = tptr._policy_failures(broken)
        self.assertIn("check_operator_approval_required:preflight-command-baseline", failures)

    def test_mutating_remediation_path_is_rejected(self) -> None:
        payload = tptr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "preflight-command-baseline":
                check["commands"].append("sudo noemaforge trixie-preflight --apply-remediation")
        failures = tptr._policy_failures(broken)
        self.assertIn("check_mutating_remediation_path_present:preflight-command-baseline", failures)

    def test_gate_evidence_report_is_bounded_and_explicit(self) -> None:
        report = tptr.validate_trixie_preflight_target_readiness_policy(tptr.load_policy())
        evidence = tptr.gate_evidence(
            report,
            artifact_uri="reports/trixie-preflight-target-readiness.json",
        )
        self.assertEqual("trixie_preflight_target_readiness", evidence["gate"])
        self.assertEqual("passed", evidence["status"])
        self.assertEqual(report["metrics"], evidence["metrics"])


if __name__ == "__main__":
    unittest.main()
