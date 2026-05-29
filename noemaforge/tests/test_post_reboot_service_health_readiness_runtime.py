#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_post_reboot_service_health_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the post-reboot service health readiness contract.
Inputs: Post-reboot service health readiness policy and runtime validator.
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

import post_reboot_service_health_readiness_runtime as prshr


class PostRebootServiceHealthReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_commands(self) -> None:
        report = prshr.validate_post_reboot_service_health_readiness_policy(prshr.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["post_reboot_service_health_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["target_machine_required"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertGreaterEqual(summary["target_command_count"], 12)
        self.assertIn("gateway_service_state", report["evidence_requirements"])
        self.assertIn("toolproxy_service_state", report["evidence_requirements"])
        self.assertIn("main_backend_service_state", report["evidence_requirements"])

    def test_main_backend_requires_manual_operator_approval(self) -> None:
        payload = prshr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "main-backend-service-health":
                check["requires_operator_approval"] = False
        failures = prshr._policy_failures(broken)
        self.assertIn("check_operator_approval_required:main-backend-service-health", failures)

    def test_toolproxy_service_probe_is_required(self) -> None:
        payload = prshr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "toolproxy-service-health":
                check["commands"] = ["systemctl is-active other.service || true"]
        failures = prshr._policy_failures(broken)
        self.assertIn("check_service_token_missing:toolproxy-service-health:noemaforge-toolproxy.service", failures)

    def test_gate_evidence_report_is_bounded_and_explicit(self) -> None:
        report = prshr.validate_post_reboot_service_health_readiness_policy(prshr.load_policy())
        evidence = prshr.gate_evidence(
            report,
            artifact_uri="reports/post-reboot-service-health-readiness.json",
        )
        self.assertEqual("post_reboot_service_health_readiness", evidence["gate"])
        self.assertEqual("passed", evidence["status"])
        self.assertEqual(report["metrics"], evidence["metrics"])


if __name__ == "__main__":
    unittest.main()
