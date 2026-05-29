#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_vault_reinventory_job_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate GUI Vault re-inventory privileged job and fallback command behavior.
Inputs: Workspace vault-reinventory-job policy and Admin GUI server runtime.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import vault_reinventory_job_runtime as vrj


class VaultReinventoryJobRuntimeTests(unittest.TestCase):
    def test_workspace_vault_reinventory_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "vault-reinventory-job-policy.json"
        report = vrj.validate_vault_reinventory_job_policy(
            vrj.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(2, report["metrics"]["script_reports"])
        self.assertEqual(2, report["metrics"]["valid_script_reports"])
        self.assertEqual(3, report["metrics"]["required_command_parts"])

    def test_offline_gui_api_returns_privileged_job_and_fallback_command(self) -> None:
        response = vrj.build_vault_reinventory_response(package_root=ROOT)
        job = response["job"]

        self.assertTrue(response["ok"], response)
        self.assertTrue(response["privilege_required"], response)
        self.assertEqual("needs_privilege", job["status"])
        self.assertEqual("vault_reinventory", job["kind"])
        self.assertEqual("vault-reinventory", job["idempotency_key"])
        self.assertEqual(response["fallback_command"], response["suggested_command"])
        self.assertEqual(response["fallback_command"], job["command"])
        self.assertIn("gui_plan_only", response["execution_policy"])

    def test_fallback_command_covers_inventory_dataset_and_eligibility_steps(self) -> None:
        response = vrj.build_vault_reinventory_response(package_root=ROOT)
        command = response["fallback_command"]
        artifacts = response["job"]["artifacts"]

        self.assertIn("sudo noemaforge inventory scan", command)
        self.assertIn("sudo noemaforge datasets scan", command)
        self.assertIn("sudo noemaforge tournament eligibility", command)
        self.assertTrue(any(item["type"] == "privileged_fallback_command" and item["command"] == command for item in artifacts))


if __name__ == "__main__":
    unittest.main()
