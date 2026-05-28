#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_post_reboot_gpu_gdm_gateway_toolproxy_readiness_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the post-reboot GPU/GDM/gateway/ToolProxy readiness contract.
Inputs: Post-reboot composite readiness policy and runtime validator.
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

import post_reboot_gpu_gdm_gateway_toolproxy_readiness_runtime as prggt


class PostRebootGpuGdmGatewayToolproxyReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_target_commands(self) -> None:
        report = prggt.validate_post_reboot_gpu_gdm_gateway_toolproxy_readiness_policy(prggt.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["post_reboot_gpu_gdm_gateway_toolproxy_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["target_machine_required"])
        self.assertTrue(summary["operator_approval_required"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertGreaterEqual(summary["target_command_count"], 20)
        self.assertIn("nvidia_smi_csv", report["evidence_requirements"])
        self.assertIn("gateway_smoke_transcript", report["evidence_requirements"])
        self.assertIn("toolproxy_smoke_json", report["evidence_requirements"])
        self.assertIn("bundle_sha256", report["evidence_requirements"])

    def test_operator_approval_is_required_for_live_smoke_and_archive_steps(self) -> None:
        broken = copy.deepcopy(prggt.load_policy())
        for check in broken["policy"]["required_checks"]:
            if check["id"] in {"socket-live-smokes", "archive-and-redaction"}:
                check["requires_operator_approval"] = False
        failures = prggt._policy_failures(broken)
        self.assertIn("check_operator_approval_required:socket-live-smokes", failures)
        self.assertIn("check_operator_approval_required:archive-and-redaction", failures)

    def test_remote_upload_path_is_rejected(self) -> None:
        broken = copy.deepcopy(prggt.load_policy())
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "archive-and-redaction":
                check["commands"].append("sudo noemaforge forensics --upload")
        failures = prggt._policy_failures(broken)
        self.assertIn("check_forbidden_token:archive-and-redaction:--upload", failures)

    def test_missing_gpu_command_is_rejected(self) -> None:
        broken = copy.deepcopy(prggt.load_policy())
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "gpu-gdm-baseline":
                check["commands"] = [item for item in check["commands"] if not item.startswith("nvidia-smi ")]
        failures = prggt._policy_failures(broken)
        self.assertIn(
            "check_command_missing:gpu-gdm-baseline:nvidia-smi --query-gpu=name,driver_version,memory.total,ecc.mode.current --format=csv,noheader",
            failures,
        )

    def test_example_validation_and_gate_evidence_are_explicit(self) -> None:
        report = prggt.validate_post_reboot_gpu_gdm_gateway_toolproxy_readiness_policy(prggt.load_policy())
        example = prggt.validate_example()
        self.assertTrue(example["ok"], example["failures"])
        evidence = prggt.gate_evidence(
            report,
            artifact_uri="reports/post-reboot-gpu-gdm-gateway-toolproxy-readiness.json",
        )
        self.assertEqual("post_reboot_gpu_gdm_gateway_toolproxy_readiness", evidence["gate"])
        self.assertEqual("passed", evidence["status"])
        self.assertEqual(report["metrics"], evidence["metrics"])


if __name__ == "__main__":
    unittest.main()
