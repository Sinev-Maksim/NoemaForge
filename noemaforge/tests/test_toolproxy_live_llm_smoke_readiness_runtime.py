#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_toolproxy_live_llm_smoke_readiness_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the ToolProxy live LLM smoke readiness contract.
Inputs: ToolProxy live LLM smoke readiness policy and runtime validator.
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

import toolproxy_live_llm_smoke_readiness_runtime as tlls


class ToolProxyLiveLlmSmokeReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_toolproxy_or_llm(self) -> None:
        report = tlls.validate_toolproxy_live_llm_smoke_readiness_policy(tlls.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["toolproxy_live_llm_smoke_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["target_machine_required"])
        self.assertTrue(summary["operator_approval_required"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertGreaterEqual(summary["target_command_count"], 9)
        self.assertIn("toolproxy_smoke_json", report["evidence_requirements"])
        self.assertIn("llm_chat_result", report["evidence_requirements"])

    def test_live_binding_and_smoke_require_operator_approval(self) -> None:
        payload = tlls.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] in {"llm-chat-scope-binding", "live-llm-smoke"}:
                check["requires_operator_approval"] = False
        failures = tlls._policy_failures(broken)
        self.assertIn("check_operator_approval_required:llm-chat-scope-binding", failures)
        self.assertIn("check_operator_approval_required:live-llm-smoke", failures)

    def test_remote_upload_or_reboot_path_is_rejected(self) -> None:
        payload = tlls.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "live-smoke-archive":
                check["commands"].extend(["sudo noemaforge forensics --upload", "sudo reboot"])
        failures = tlls._policy_failures(broken)
        self.assertIn("check_forbidden_token:live-smoke-archive:--upload", failures)
        self.assertIn("check_forbidden_token:live-smoke-archive:reboot", failures)

    def test_gate_evidence_report_is_bounded_and_explicit(self) -> None:
        report = tlls.validate_toolproxy_live_llm_smoke_readiness_policy(tlls.load_policy())
        evidence = tlls.gate_evidence(
            report,
            artifact_uri="reports/toolproxy-live-llm-smoke-readiness.json",
        )
        self.assertEqual("toolproxy_live_llm_smoke_readiness", evidence["gate"])
        self.assertEqual("passed", evidence["status"])
        self.assertEqual(report["metrics"], evidence["metrics"])


if __name__ == "__main__":
    unittest.main()
