#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_clean_distribution_allowlist_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate public distribution allowlist and core/optional split invariants.
Inputs: Workspace clean-distribution policy and temporary broken fixtures.
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

import clean_distribution_allowlist_runtime as cdar
import production_ai_contracts as pac


class CleanDistributionAllowlistRuntimeTests(unittest.TestCase):
    def test_workspace_clean_distribution_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "clean-distribution-allowlist.json"
        report = cdar.validate_clean_distribution_policy(
            cdar.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["plans"])
        self.assertEqual(1, report["metrics"]["passing_plans"])
        self.assertEqual(4, report["metrics"]["category_rules"])
        self.assertEqual(6, report["metrics"]["required_core_refs"])

        gate = pac.evaluate_gate(
            {"change_id": "clean-distribution-allowlist-core", "domain": "pipeline"},
            cdar.clean_distribution_report_to_gate_evidence(report, artifact_uri="reports/clean-distribution-allowlist.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_optional_hf_material_cannot_enter_core_seed(self) -> None:
        policy_path = ROOT / "configs" / "clean-distribution-allowlist.json"
        policy = cdar.load_policy(policy_path)
        example_set = cdar.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "clean_distribution_allowlist.example.json")
        broken_set = copy.deepcopy(example_set)
        broken_set["plans"][0]["included_refs"].append("noemaforge/configs/hfbridge-metadata-policy.json")

        with patch.object(cdar, "load_example_set", return_value=broken_set):
            report = cdar.validate_clean_distribution_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn(
            "plan_core_ref_matches_excluded_prefix:public-core-seed-dry-run:hf:noemaforge/configs/hfbridge-metadata-policy.json",
            report["failures"],
        )

    def test_plan_cannot_delete_or_skip_allowlist_mode(self) -> None:
        policy_path = ROOT / "configs" / "clean-distribution-allowlist.json"
        policy = cdar.load_policy(policy_path)
        example_set = cdar.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "clean_distribution_allowlist.example.json")
        broken_set = copy.deepcopy(example_set)
        broken_set["plans"][0]["allowlist_only"] = False
        broken_set["plans"][0]["deletes_files"] = True

        with patch.object(cdar, "load_example_set", return_value=broken_set):
            report = cdar.validate_clean_distribution_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("plan_allowlist_only_not_true:public-core-seed-dry-run", report["failures"])
        self.assertIn("plan_deletes_files_not_false:public-core-seed-dry-run", report["failures"])

    def test_required_core_refs_must_be_present(self) -> None:
        policy_path = ROOT / "configs" / "clean-distribution-allowlist.json"
        policy = cdar.load_policy(policy_path)
        example_set = cdar.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "clean_distribution_allowlist.example.json")
        broken_set = copy.deepcopy(example_set)
        broken_set["plans"][0]["included_refs"].remove("VERSION")

        with patch.object(cdar, "load_example_set", return_value=broken_set):
            report = cdar.validate_clean_distribution_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("plan_required_core_ref_missing:public-core-seed-dry-run:VERSION", report["failures"])


if __name__ == "__main__":
    unittest.main()
