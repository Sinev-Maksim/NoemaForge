#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_public_autonomy_boundary_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate public autonomy boundary runtime behavior.
Inputs: Workspace public-autonomy-boundary and self-improvement policies.
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
import public_autonomy_boundary_runtime as pabr


class PublicAutonomyBoundaryRuntimeTests(unittest.TestCase):
    def test_workspace_public_autonomy_boundary_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "public-autonomy-boundary-policy.json"
        validation = pabr.validate_public_autonomy_boundary_policy(
            pabr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])
        self.assertGreaterEqual(validation["metrics"]["boundary_refs"], 8)

        gate = pac.evaluate_gate(
            {"change_id": "public-autonomy-boundary-core", "domain": "pipeline"},
            pabr.public_autonomy_boundary_report_to_gate_evidence(validation, artifact_uri="reports/public-autonomy-boundary.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_self_improvement_policy_requires_measured_review_and_admin_approval(self) -> None:
        policy = pabr.load_self_improvement_policy(ROOT / "configs" / "self-improvement-policy.json")
        auto = policy["auto_rollback"]
        self.assertEqual("measured_review", policy["default_mode"])
        self.assertFalse(auto["enabled_by_default"])
        self.assertTrue(auto["block_apply_on_failed_cases"])
        self.assertTrue(auto["block_apply_on_resource_regression"])
        self.assertTrue(auto["requires_admin_approval"])

    def test_public_boundary_examples_reject_marketing_claims(self) -> None:
        policy = pabr.load_policy(ROOT / "configs" / "public-autonomy-boundary-policy.json")
        contract = policy["policy"]
        examples = pabr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "public_autonomy_boundary.example.json")
        scenario = examples["scenarios"][0]
        self.assertIn(contract["boundary_phrase"], scenario["allowed_copy"])
        self.assertIn("alpha/lab-only", scenario["allowed_copy"])
        self.assertIn("approval-gated", scenario["allowed_copy"])
        self.assertIn("no automatic apply", scenario["allowed_copy"])
        for claim in scenario["rejected_claims"]:
            self.assertIn(claim, contract["blocked_public_claims"])

    def test_scanned_public_docs_do_not_contain_blocked_claims(self) -> None:
        policy = pabr.load_policy(ROOT / "configs" / "public-autonomy-boundary-policy.json")
        report = pabr.validate_public_autonomy_boundary_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertEqual([], report["docs"]["failures"])


if __name__ == "__main__":
    unittest.main()
