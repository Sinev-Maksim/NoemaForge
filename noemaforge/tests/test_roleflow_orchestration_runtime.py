#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_roleflow_orchestration_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate RoleFlow orchestration graph invariants.
Inputs: Workspace RoleFlow policy and temporary broken fixtures.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import production_ai_contracts as pac
import roleflow_orchestration_runtime as rfor


class RoleFlowOrchestrationRuntimeTests(unittest.TestCase):
    def test_workspace_roleflow_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "roleflow-orchestration-policy.json"
        report = rfor.validate_roleflow_policy(
            rfor.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["flows"])
        self.assertEqual(1, report["metrics"]["passing_flows"])
        self.assertEqual(4, report["metrics"]["kernel_roles"])
        self.assertEqual(3, report["metrics"]["approval_roles"])

        gate = pac.evaluate_gate(
            {"change_id": "roleflow-orchestration-core", "domain": "pipeline"},
            rfor.roleflow_report_to_gate_evidence(report, artifact_uri="reports/roleflow-orchestration.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_approval_edge_requires_allowed_approver_role(self) -> None:
        policy_path = ROOT / "configs" / "roleflow-orchestration-policy.json"
        policy = rfor.load_policy(policy_path)
        example_set = rfor.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "roleflow_orchestration.example.json")
        broken_set = copy.deepcopy(example_set)
        broken_set["flows"][0]["orchestration_graph"]["edges"][2]["approver_role"] = "dev.work/dev"

        with patch.object(rfor, "load_example_set", return_value=broken_set):
            report = rfor.validate_roleflow_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn(
            "flow_approval_edge_approver_invalid:roleflow-admin-scary-surgeon-repair:edge:approval-to-surgeon:dev.work/dev",
            report["failures"],
        )

    def test_rollback_edge_requires_valid_target(self) -> None:
        policy_path = ROOT / "configs" / "roleflow-orchestration-policy.json"
        policy = rfor.load_policy(policy_path)
        example_set = rfor.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "roleflow_orchestration.example.json")
        broken_set = copy.deepcopy(example_set)
        broken_set["flows"][0]["orchestration_graph"]["edges"][5]["rollback_target"] = "missing_node"

        with patch.object(rfor, "load_example_set", return_value=broken_set):
            report = rfor.validate_roleflow_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn(
            "flow_rollback_edge_target_invalid:roleflow-admin-scary-surgeon-repair:edge:branch-to-rollback:missing_node",
            report["failures"],
        )

    def test_baton_payload_is_required(self) -> None:
        policy_path = ROOT / "configs" / "roleflow-orchestration-policy.json"
        policy = rfor.load_policy(policy_path)
        example_set = rfor.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "roleflow_orchestration.example.json")
        broken_set = copy.deepcopy(example_set)
        del broken_set["flows"][0]["orchestration_graph"]["batons"][0]["payload"]

        with patch.object(rfor, "load_example_set", return_value=broken_set):
            report = rfor.validate_roleflow_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn(
            "flow_baton_required_fields_missing:roleflow-admin-scary-surgeon-repair:baton:roleflow:surgeon-repair:payload",
            report["failures"],
        )
        self.assertIn(
            "flow_baton_payload_invalid:roleflow-admin-scary-surgeon-repair:baton:roleflow:surgeon-repair",
            report["failures"],
        )


if __name__ == "__main__":
    unittest.main()
