#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_clean_install_share_readiness_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test the clean install share readiness contract.
Inputs: Clean install share readiness policy and runtime validator.
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

import clean_install_share_readiness_runtime as cis


class CleanInstallShareReadinessRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes_without_live_install(self) -> None:
        report = cis.validate_clean_install_share_readiness_policy(cis.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["clean_install_readiness_summary"]
        self.assertTrue(summary["completion_blocked"])
        self.assertTrue(summary["safe_local_validator_only"])
        self.assertEqual("/mnt/noemaforge-share", summary["canonical_share_root"])
        self.assertGreaterEqual(summary["target_command_count"], 10)
        self.assertIn("nofail", report["share_mount_requirements"]["required_fstab_options"])

    def test_host_install_requires_operator_approval(self) -> None:
        payload = cis.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "host-clean-install":
                check["requires_operator_approval"] = False
        failures = cis._policy_failures(broken)
        self.assertIn("check_host_install_without_operator_approval", failures)

    def test_share_mount_requires_nofail_automount_gate(self) -> None:
        payload = cis.load_policy()
        broken = copy.deepcopy(payload)
        for check in broken["policy"]["required_checks"]:
            if check["id"] == "share-mount-normalization":
                check["completion_gates"] = ["share_path_is_canonical", "evidence_file_archived"]
        failures = cis._policy_failures(broken)
        self.assertIn("check_share_nofail_automount_gate_missing", failures)


if __name__ == "__main__":
    unittest.main()
