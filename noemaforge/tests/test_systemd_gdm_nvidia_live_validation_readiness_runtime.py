#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_systemd_gdm_nvidia_live_validation_readiness_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the systemd/GDM/NVIDIA live-validation readiness contract.
Inputs: Systemd/GDM/NVIDIA live-validation readiness policy and runtime validator.
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

import systemd_gdm_nvidia_live_validation_readiness_runtime as sgnv


class SystemdGdmNvidiaLiveValidationReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_target_commands(self) -> None:
        report = sgnv.validate_systemd_gdm_nvidia_live_validation_readiness_policy(sgnv.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["systemd_gdm_nvidia_live_validation_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["target_machine_required"])
        self.assertTrue(summary["operator_approval_required"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertGreaterEqual(summary["target_command_count"], 15)
        self.assertIn("display_manager_state", report["evidence_requirements"])
        self.assertIn("nvidia_smi_exit_code", report["evidence_requirements"])

    def test_archive_requires_operator_approval(self) -> None:
        payload = sgnv.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "evidence-archive":
                check["requires_operator_approval"] = False
        failures = sgnv._policy_failures(broken)
        self.assertIn("check_operator_approval_required:evidence-archive", failures)

    def test_reboot_or_upload_path_is_rejected(self) -> None:
        payload = sgnv.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "evidence-archive":
                check["commands"].extend(["sudo noemaforge forensics --upload", "sudo reboot"])
        failures = sgnv._policy_failures(broken)
        self.assertIn("check_forbidden_token:evidence-archive:--upload", failures)
        self.assertIn("check_forbidden_token:evidence-archive:reboot", failures)

    def test_gate_evidence_report_is_bounded_and_explicit(self) -> None:
        report = sgnv.validate_systemd_gdm_nvidia_live_validation_readiness_policy(sgnv.load_policy())
        evidence = sgnv.gate_evidence(
            report,
            artifact_uri="reports/systemd-gdm-nvidia-live-validation-readiness.json",
        )
        self.assertEqual("systemd_gdm_nvidia_live_validation_readiness", evidence["gate"])
        self.assertEqual("passed", evidence["status"])
        self.assertEqual(report["metrics"], evidence["metrics"])


if __name__ == "__main__":
    unittest.main()
