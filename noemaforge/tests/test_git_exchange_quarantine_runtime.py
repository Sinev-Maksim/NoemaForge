#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_git_exchange_quarantine_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate quarantine-first git_exchange invariants.
Inputs: Workspace git_exchange policy and temporary broken fixtures.
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

import git_exchange_quarantine_runtime as geqr
import production_ai_contracts as pac


class GitExchangeQuarantineRuntimeTests(unittest.TestCase):
    def test_workspace_git_exchange_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "git-exchange-quarantine-policy.json"
        report = geqr.validate_git_exchange_policy(
            geqr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(6, report["metrics"]["imports"])
        self.assertEqual(6, report["metrics"]["passing_imports"])
        self.assertEqual(6, report["metrics"]["pack_kinds"])
        self.assertEqual(1, report["metrics"]["model_delta_imports"])

        gate = pac.evaluate_gate(
            {"change_id": "git-exchange-quarantine-core", "domain": "pipeline"},
            geqr.git_exchange_report_to_gate_evidence(report, artifact_uri="reports/git-exchange-quarantine.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_active_activation_state_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "git-exchange-quarantine-policy.json"
        policy = geqr.load_policy(policy_path)
        example_set = geqr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "git_exchange_quarantine.example.json")
        broken_set = copy.deepcopy(example_set)
        broken_set["imports"][0]["quarantine"]["activation_state"] = "active"

        with patch.object(geqr, "load_example_set", return_value=broken_set):
            report = geqr.validate_git_exchange_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("import_activation_blocked_state:git-exchange-rolepack-sample:active", report["failures"])

    def test_model_delta_pack_must_stay_lab_only(self) -> None:
        policy_path = ROOT / "configs" / "git-exchange-quarantine-policy.json"
        policy = geqr.load_policy(policy_path)
        example_set = geqr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "git_exchange_quarantine.example.json")
        broken_set = copy.deepcopy(example_set)
        model_delta = broken_set["imports"][-1]["model_delta"]
        model_delta["lab_only"] = False
        model_delta["production_activation_allowed"] = True

        with patch.object(geqr, "load_example_set", return_value=broken_set):
            report = geqr.validate_git_exchange_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("import_model_delta_not_lab_only:git-exchange-modeldelta-sample", report["failures"])
        self.assertIn("import_model_delta_production_activation_allowed:git-exchange-modeldelta-sample", report["failures"])

    def test_unsigned_pack_or_missing_scary_verdict_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "git-exchange-quarantine-policy.json"
        policy = geqr.load_policy(policy_path)
        example_set = geqr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "git_exchange_quarantine.example.json")
        broken_set = copy.deepcopy(example_set)
        broken_set["imports"][1]["signed_manifest"] = False
        broken_set["imports"][1]["review"]["scary_verdict"] = "approve"

        with patch.object(geqr, "load_example_set", return_value=broken_set):
            report = geqr.validate_git_exchange_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("import_signed_manifest_missing:git-exchange-roleflow-sample", report["failures"])
        self.assertIn("import_scary_verdict_invalid:git-exchange-roleflow-sample:approve", report["failures"])


if __name__ == "__main__":
    unittest.main()
