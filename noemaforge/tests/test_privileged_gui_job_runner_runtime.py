#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_privileged_gui_job_runner_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate the approval-gated privileged GUI job runner contract.
Inputs: Workspace privileged GUI job-runner policy, Admin GUI server and example fixtures.
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

import privileged_gui_job_runner as pgr
import production_ai_contracts as pac


class PrivilegedGuiJobRunnerRuntimeTests(unittest.TestCase):
    def test_workspace_privileged_gui_job_runner_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "privileged-gui-job-runner-policy.json"
        validation = pgr.validate_privileged_gui_job_runner_policy(
            pgr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(4, validation["metrics"]["examples"])
        self.assertEqual(4, validation["metrics"]["passing_examples"])
        self.assertEqual(3, validation["metrics"]["checked_allowed_jobs"])

        gate = pac.evaluate_gate(
            {"change_id": "privileged-gui-job-runner-core", "domain": "pipeline"},
            pgr.privileged_gui_job_runner_report_to_gate_evidence(validation, artifact_uri="reports/privileged-gui-job-runner.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_admin_epoch_apply_job_contains_dry_run_polkit_runner(self) -> None:
        policy = pgr.load_policy(ROOT / "configs" / "privileged-gui-job-runner-policy.json")
        built = pgr.build_epoch_apply_response(package_root=ROOT)
        response = built["response"]
        job = response["job"]
        runner = job["privileged_runner"]

        self.assertEqual("needs_privilege", job["status"])
        self.assertEqual("epoch_apply", job["kind"])
        self.assertIn("--keep-display", job["command"])
        self.assertEqual("polkit_approval_required", runner["policy"])
        self.assertEqual("org.noemaforge.privileged-jobs.run", runner["polkit_action"])
        self.assertTrue(runner["dry_run_default"])
        self.assertIn("--dry-run", runner["runner_command"])
        self.assertIn("privileged-job run", runner["runner_command"])

        result = pgr.run_privileged_job(job, policy, approval_token=runner["approval_token"], dry_run=True)
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["executed"])

    def test_continue_selection_and_vault_jobs_contain_polkit_runner(self) -> None:
        policy = pgr.load_policy(ROOT / "configs" / "privileged-gui-job-runner-policy.json")
        continue_built = pgr.build_model_selection_continue_response(package_root=ROOT)
        continue_job = continue_built["response"]["job"]
        continue_runner = continue_job["privileged_runner"]

        self.assertEqual("model_selection_continue", continue_job["kind"])
        self.assertEqual("first_start_model_selection_continue", continue_job["allowed_action"])
        self.assertIn("--dry-run", continue_job["command"])
        self.assertIn("--keep-display", continue_job["command"])
        continue_result = pgr.run_privileged_job(continue_job, policy, approval_token=continue_runner["approval_token"], dry_run=True)
        self.assertTrue(continue_result["ok"], continue_result)

        vault_built = pgr.build_vault_reinventory_response(package_root=ROOT)
        vault_job = vault_built["response"]["job"]
        vault_runner = vault_job["privileged_runner"]

        self.assertEqual("vault_reinventory", vault_job["kind"])
        self.assertEqual("vault_reinventory_scan", vault_job["allowed_action"])
        self.assertEqual(3, len(vault_job["privileged_steps"]))
        self.assertIn("&&", vault_job["command"])
        vault_result = pgr.run_privileged_job(vault_job, policy, approval_token=vault_runner["approval_token"], dry_run=True)
        self.assertTrue(vault_result["ok"], vault_result)
        self.assertEqual(vault_job["privileged_steps"], vault_result["would_execute_steps"])

    def test_runner_blocks_shell_fragments_and_unapproved_apply(self) -> None:
        policy = pgr.load_policy(ROOT / "configs" / "privileged-gui-job-runner-policy.json")
        safe_job = {
            "job_id": "job_20260520T194954Z_epoch_apply",
            "kind": "epoch_apply",
            "status": "needs_privilege",
            "command": "sudo noemaforge first-start --normal --keep-display",
            "allowed_action": "first_start_epoch_apply",
            "approval_state": "pending_operator_review",
            "polkit_action": "org.noemaforge.privileged-jobs.run",
        }
        safe_job["approval_token"] = pgr.approval_token_for_job(safe_job)
        dry_run = pgr.run_privileged_job(safe_job, policy, approval_token=safe_job["approval_token"], dry_run=True)
        self.assertTrue(dry_run["ok"], dry_run)

        apply = pgr.run_privileged_job(safe_job, policy, approval_token=safe_job["approval_token"], dry_run=False)
        self.assertFalse(apply["ok"], apply)
        self.assertIn("job_approval_state_not_approved_for_apply", apply["failures"])

        unsafe_job = dict(safe_job)
        unsafe_job["job_id"] = "job_20260520T194954Z_shell_fragment"
        unsafe_job["command"] = "sudo noemaforge first-start --normal --keep-display; reboot"
        unsafe_job["approval_state"] = "approved"
        unsafe_job["approval_token"] = pgr.approval_token_for_job(unsafe_job)
        rejected = pgr.run_privileged_job(unsafe_job, policy, approval_token=unsafe_job["approval_token"], dry_run=True)
        self.assertFalse(rejected["ok"], rejected)
        self.assertIn("command_forbidden_fragment:;", rejected["failures"])


if __name__ == "__main__":
    unittest.main()
