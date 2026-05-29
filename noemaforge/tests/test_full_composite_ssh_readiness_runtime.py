#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_full_composite_ssh_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the patched10 full-composite SSH readiness contract.
Inputs: Full composite SSH readiness policy and runtime validator.
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

import full_composite_ssh_readiness_runtime as fcsr


class FullCompositeSshReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_ssh(self) -> None:
        report = fcsr.validate_full_composite_ssh_readiness_policy(fcsr.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["ssh_readiness_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertTrue(summary["target_machine_required"])
        self.assertGreaterEqual(summary["target_command_count"], 7)
        self.assertIn("ssh_session_transcript", report["evidence_requirements"])

    def test_ssh_run_requires_operator_approval(self) -> None:
        payload = fcsr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "full-composite-ssh-watch":
                check["requires_operator_approval"] = False
        failures = fcsr._policy_failures(broken)
        self.assertIn("check_operator_approval_required:full-composite-ssh-watch", failures)

    def test_secure_access_requires_fingerprint_and_no_secrets(self) -> None:
        payload = fcsr.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "secure-access-plan":
                check["evidence"] = ["operator_approved_ssh_identity"]
        failures = fcsr._policy_failures(broken)
        self.assertIn("check_access_evidence_missing:known_host_fingerprint", failures)
        self.assertIn("check_access_evidence_missing:no_plaintext_credentials", failures)


if __name__ == "__main__":
    unittest.main()
