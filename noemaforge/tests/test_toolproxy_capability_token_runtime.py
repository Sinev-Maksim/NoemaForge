#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_toolproxy_capability_token_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate ToolProxy capability-token issuance UX invariants.
Inputs: Workspace ToolProxy capability-token policy and offline token fixtures.
Outputs: unittest assertions only.
Side effects: Creates temporary token records in an isolated test directory.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import production_ai_contracts as pac
import toolproxy_capability_token_runtime as tctr


class ToolProxyCapabilityTokenRuntimeTests(unittest.TestCase):
    def test_workspace_toolproxy_capability_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "toolproxy-capability-token-policy.json"
        report = tctr.validate_toolproxy_capability_policy(
            tctr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["flows"])
        self.assertEqual(1, report["metrics"]["passing_flows"])
        self.assertEqual(5, report["metrics"]["required_ux_commands"])

        gate = pac.evaluate_gate(
            {"change_id": "toolproxy-capability-token-core", "domain": "pipeline"},
            tctr.toolproxy_capability_report_to_gate_evidence(report, artifact_uri="reports/toolproxy-capability-token.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_offline_token_cycle_issues_lists_verifies_revokes_and_redacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toolproxy-cap-", dir=os.path.dirname(__file__)) as tmp:
            result = tctr.run_offline_token_cycle(tmp)

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["token_redacted"].endswith(".***"))
        self.assertEqual(1, result["listing"]["count"])
        self.assertTrue(result["verify"]["ok"])
        self.assertEqual("ok", result["verify"]["reason"])
        self.assertTrue(result["revoke"]["ok"])
        self.assertFalse(result["post_revoke_verify"]["ok"])
        self.assertEqual("unknown_token", result["post_revoke_verify"]["reason"])

    def test_plaintext_persisted_secret_breaks_contract(self) -> None:
        policy_path = ROOT / "configs" / "toolproxy-capability-token-policy.json"
        policy = tctr.load_policy(policy_path)
        example = tctr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "toolproxy_capability_token.example.json")
        broken = copy.deepcopy(example)
        broken["flows"][0]["record"]["secret"] = "plain-secret"

        with patch.object(tctr, "load_example_set", return_value=broken):
            report = tctr.validate_toolproxy_capability_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertFalse(report["ok"])
        self.assertIn("flow_record_plaintext_secret:offline-issue-list-verify-revoke-smoke", report["failures"])

    def test_default_issue_output_must_stay_redacted(self) -> None:
        policy_path = ROOT / "configs" / "toolproxy-capability-token-policy.json"
        policy = tctr.load_policy(policy_path)
        example = tctr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "toolproxy_capability_token.example.json")
        broken = copy.deepcopy(example)
        broken["flows"][0]["issue"]["show_secret"] = True
        broken["flows"][0]["issue"]["token_output"] = "tok-example.plain-secret"

        with patch.object(tctr, "load_example_set", return_value=broken):
            report = tctr.validate_toolproxy_capability_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertFalse(report["ok"])
        self.assertIn("flow_issue_show_secret_not_false:offline-issue-list-verify-revoke-smoke", report["failures"])
        self.assertIn("flow_issue_token_not_redacted:offline-issue-list-verify-revoke-smoke", report["failures"])


if __name__ == "__main__":
    unittest.main()
