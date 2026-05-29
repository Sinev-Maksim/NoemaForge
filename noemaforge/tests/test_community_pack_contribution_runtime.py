#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_community_pack_contribution_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate community pack contribution runtime behavior.
Inputs: Workspace community contribution policy, quarantine policy and clean distribution policy.
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

import community_pack_contribution_runtime as cpcr
import production_ai_contracts as pac


class CommunityPackContributionRuntimeTests(unittest.TestCase):
    def test_workspace_community_pack_contribution_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "community-pack-contribution-policy.json"
        validation = cpcr.validate_community_pack_contribution_policy(
            cpcr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])
        self.assertGreaterEqual(validation["metrics"]["manifest_fields"], 8)

        gate = pac.evaluate_gate(
            {"change_id": "community-pack-contribution-core", "domain": "pipeline"},
            cpcr.community_pack_contribution_report_to_gate_evidence(validation, artifact_uri="reports/community-pack-contribution.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_git_exchange_policy_carries_quarantine_first_requirements(self) -> None:
        policy = cpcr.load_policy(ROOT / "configs" / "community-pack-contribution-policy.json")
        validation = cpcr.validate_community_pack_contribution_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(validation["ok"], validation["failures"])

        quarantine = validation["quarantine_policy"]
        self.assertEqual("git-exchange-quarantine-core", quarantine["policy_id"])
        self.assertEqual([], quarantine["failures"])

    def test_examples_accept_reviewed_quarantine_and_reject_unsafe_paths(self) -> None:
        policy = cpcr.load_policy(ROOT / "configs" / "community-pack-contribution-policy.json")
        examples = cpcr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "community_pack_contribution.example.json")
        validation = cpcr.validate_community_pack_contribution_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertTrue(validation["ok"], validation["failures"])
        scenario = examples["scenarios"][0]
        accepted = scenario["accepted_pack"]
        self.assertEqual("quarantined", accepted["activation_state"])
        for field in policy["policy"]["required_manifest_fields"]:
            self.assertIn(field, accepted["manifest"])
        rejected_claims = "\n".join(pack["claim"] for pack in scenario["rejected_packs"])
        self.assertIn("install community pack directly into active runtime", rejected_claims)
        self.assertIn("skip quarantine for community pack", rejected_claims)
        self.assertIn("promote ModelDeltaPack into public core", rejected_claims)

    def test_docs_scan_has_no_blocked_public_claims(self) -> None:
        policy = cpcr.load_policy(ROOT / "configs" / "community-pack-contribution-policy.json")
        validation = cpcr.validate_community_pack_contribution_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(validation["ok"], validation["failures"])
        for item in validation["docs"]["scan_reports"]:
            self.assertTrue(item["ok"], item)


if __name__ == "__main__":
    unittest.main()
