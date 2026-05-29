#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_gateway_main_live_smoke_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the gateway/main live-smoke readiness contract.
Inputs: Gateway/main live-smoke readiness policy and runtime validator.
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

import gateway_main_live_smoke_readiness_runtime as gmls


class GatewayMainLiveSmokeReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_gateway_or_llm(self) -> None:
        report = gmls.validate_gateway_main_live_smoke_readiness_policy(gmls.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["gateway_main_live_smoke_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["target_machine_required"])
        self.assertTrue(summary["operator_approval_required"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertGreaterEqual(summary["target_command_count"], 10)
        self.assertIn("gateway_smoke_transcript", report["evidence_requirements"])
        self.assertIn("chat_completion_transcript", report["evidence_requirements"])

    def test_manual_start_and_chat_smoke_require_operator_approval(self) -> None:
        payload = gmls.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] in {"main-backend-manual-start", "gateway-chat-smoke"}:
                check["requires_operator_approval"] = False
        failures = gmls._policy_failures(broken)
        self.assertIn("check_operator_approval_required:main-backend-manual-start", failures)
        self.assertIn("check_operator_approval_required:gateway-chat-smoke", failures)

    def test_remote_upload_path_is_rejected(self) -> None:
        payload = gmls.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "backend-stop-and-archive":
                check["commands"].append("sudo noemaforge forensics --upload")
        failures = gmls._policy_failures(broken)
        self.assertIn("check_forbidden_token:backend-stop-and-archive:--upload", failures)

    def test_gate_evidence_report_is_bounded_and_explicit(self) -> None:
        report = gmls.validate_gateway_main_live_smoke_readiness_policy(gmls.load_policy())
        evidence = gmls.gate_evidence(
            report,
            artifact_uri="reports/gateway-main-live-smoke-readiness.json",
        )
        self.assertEqual("gateway_main_live_smoke_readiness", evidence["gate"])
        self.assertEqual("passed", evidence["status"])
        self.assertEqual(report["metrics"], evidence["metrics"])


if __name__ == "__main__":
    unittest.main()
