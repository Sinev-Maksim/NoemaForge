#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_role_review_state_machine_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Admin/Surgeon/Scary state-machine runtime behavior.
Inputs: Workspace role review state-machine policy, role kernel, roleflow policy and examples.
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

import production_ai_contracts as pac
import role_review_state_machine_runtime as rrsm


class RoleReviewStateMachineRuntimeTests(unittest.TestCase):
    def test_workspace_role_review_state_machine_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "role-review-state-machine-policy.json"
        validation = rrsm.validate_role_review_state_machine_policy(
            rrsm.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])
        self.assertEqual(3, validation["metrics"]["required_roles"])

        gate = pac.evaluate_gate(
            {"change_id": "role-review-state-machine-core", "domain": "pipeline"},
            rrsm.role_review_state_machine_report_to_gate_evidence(validation, artifact_uri="reports/role-review-state-machine.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_role_dependencies_cover_admin_scary_and_surgeon(self) -> None:
        policy = rrsm.load_policy(ROOT / "configs" / "role-review-state-machine-policy.json")
        validation = rrsm.validate_role_review_state_machine_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual([], validation["roles"]["failures"])
        self.assertTrue(validation["roles"]["role_kernel"]["ok"])
        self.assertTrue(validation["roles"]["roleflow"]["ok"])

    def test_examples_model_guarded_admin_surgeon_scary_state_order(self) -> None:
        policy = rrsm.load_policy(ROOT / "configs" / "role-review-state-machine-policy.json")
        examples = rrsm.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "role_review_state_machine.example.json")
        validation = rrsm.validate_role_review_state_machine_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertTrue(validation["ok"], validation["failures"])
        scenario = examples["scenarios"][0]
        self.assertEqual(["admin_intake", "scary_risk_review", "admin_decision"], scenario["accepted_trace"][:3])
        self.assertIn("surgeon_repair_plan", scenario["accepted_trace"])
        self.assertEqual("applied", scenario["accepted_trace"][-1])
        baton = scenario["state_machine"]["batons"][0]
        self.assertEqual(("admin_decision", "surgeon_repair_plan"), (baton["from_state"], baton["to_state"]))
        self.assertTrue(baton["durable"])
        self.assertTrue(baton["sleep_wake"])

    def test_examples_reject_skipped_guards_and_auto_apply(self) -> None:
        policy = rrsm.load_policy(ROOT / "configs" / "role-review-state-machine-policy.json")
        examples = rrsm.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "role_review_state_machine.example.json")
        claims = "\n".join(item["claim"] for item in examples["scenarios"][0]["rejected_transitions"])

        self.assertIn("skip scary review", claims)
        self.assertIn("surgeon applies without admin approval", claims)
        self.assertIn("auto-apply repair plan", claims)
        validation = rrsm.validate_role_review_state_machine_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        for item in validation["docs"]["scan_reports"]:
            self.assertTrue(item["ok"], item)


if __name__ == "__main__":
    unittest.main()
