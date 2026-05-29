#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_role_kernel_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate protected role kernel and ActiveNN one-heavy-worker invariants.
Inputs: Workspace Role Kernel policy and temporary broken fixtures.
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
import role_kernel_runtime as rkr


class RoleKernelRuntimeTests(unittest.TestCase):
    def test_workspace_role_kernel_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "role-kernel-policy.json"
        report = rkr.validate_role_kernel_policy(
            rkr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["kernels"])
        self.assertEqual(1, report["metrics"]["passing_kernels"])
        self.assertEqual(4, report["metrics"]["default_roles"])
        self.assertEqual(19, report["metrics"]["optional_rolepacks"])
        self.assertEqual(2, report["metrics"]["heavy_default_roles"])

        gate = pac.evaluate_gate(
            {"change_id": "role-kernel-active-nn-core", "domain": "pipeline"},
            rkr.role_kernel_report_to_gate_evidence(report, artifact_uri="reports/role-kernel.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_optional_rolepack_activation_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "role-kernel-policy.json"
        policy = rkr.load_policy(policy_path)
        broken_policy = copy.deepcopy(policy)
        broken_policy["policy"]["optional_rolepacks"][0]["activation"] = "active"

        report = rkr.validate_role_kernel_policy(
            broken_policy,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("policy_optional_rolepack_active:system.guard/ssr", report["failures"])

    def test_two_active_heavy_workers_are_blocked(self) -> None:
        policy_path = ROOT / "configs" / "role-kernel-policy.json"
        policy = rkr.load_policy(policy_path)
        example_set = rkr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "role_kernel.example.json")
        broken_set = copy.deepcopy(example_set)
        broken_set["kernels"][0]["active_heavy_workers"] = ["system.guard/surgeon", "selfdev.learning/coach"]

        with patch.object(rkr, "load_example_set", return_value=broken_set):
            report = rkr.validate_role_kernel_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("kernel_too_many_active_heavy_workers:role-kernel-default-four:2", report["failures"])

    def test_default_role_missing_from_persona_catalog_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "role-kernel-policy.json"
        policy = rkr.load_policy(policy_path)
        broken_policy = copy.deepcopy(policy)
        broken_policy["policy"]["default_roles"][3]["role_key"] = "selfdev.evolve/darwin"

        report = rkr.validate_role_kernel_policy(
            broken_policy,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("persona_default_role_missing:selfdev.evolve/darwin", report["failures"])


if __name__ == "__main__":
    unittest.main()
