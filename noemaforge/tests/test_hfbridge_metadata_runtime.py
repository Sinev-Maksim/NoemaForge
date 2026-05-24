#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_hfbridge_metadata_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate HFBridge metadata-first/read-mostly invariants.
Inputs: Workspace HFBridge policy and temporary broken fixtures.
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

import hfbridge_metadata_runtime as hmr
import production_ai_contracts as pac


class HFBridgeMetadataRuntimeTests(unittest.TestCase):
    def test_workspace_hfbridge_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "hfbridge-metadata-policy.json"
        report = hmr.validate_hfbridge_policy(
            hmr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(2, report["metrics"]["queries"])
        self.assertEqual(2, report["metrics"]["passing_queries"])
        self.assertEqual(5, report["metrics"]["allowed_operations"])
        self.assertEqual(6, report["metrics"]["blocked_operations"])

        gate = pac.evaluate_gate(
            {"change_id": "hfbridge-metadata-core", "domain": "pipeline"},
            hmr.hfbridge_report_to_gate_evidence(report, artifact_uri="reports/hfbridge-metadata.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_weight_download_operation_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "hfbridge-metadata-policy.json"
        policy = hmr.load_policy(policy_path)
        example_set = hmr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "hfbridge_metadata.example.json")
        broken_set = copy.deepcopy(example_set)
        broken_set["queries"][0]["operation"] = "weight_download"

        with patch.object(hmr, "load_example_set", return_value=broken_set):
            report = hmr.validate_hfbridge_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("query_operation_not_allowed:hfbridge-model-card-summary:weight_download", report["failures"])
        self.assertIn("query_operation_blocked:hfbridge-model-card-summary:weight_download", report["failures"])

    def test_artifact_import_or_runtime_activation_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "hfbridge-metadata-policy.json"
        policy = hmr.load_policy(policy_path)
        example_set = hmr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "hfbridge_metadata.example.json")
        broken_set = copy.deepcopy(example_set)
        query = broken_set["queries"][0]
        query["downloads_artifacts"] = True
        query["imports_weights"] = True
        query["activates_runtime"] = True

        with patch.object(hmr, "load_example_set", return_value=broken_set):
            report = hmr.validate_hfbridge_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("query_downloads_artifacts_not_false:hfbridge-model-card-summary", report["failures"])
        self.assertIn("query_imports_weights_not_false:hfbridge-model-card-summary", report["failures"])
        self.assertIn("query_activates_runtime_not_false:hfbridge-model-card-summary", report["failures"])

    def test_promotion_request_is_blocked_for_metadata_query(self) -> None:
        policy_path = ROOT / "configs" / "hfbridge-metadata-policy.json"
        policy = hmr.load_policy(policy_path)
        example_set = hmr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "hfbridge_metadata.example.json")
        broken_set = copy.deepcopy(example_set)
        broken_set["queries"][1]["promotion"]["requested"] = True
        broken_set["queries"][1]["promotion"]["admin_approval_required"] = False

        with patch.object(hmr, "load_example_set", return_value=broken_set):
            report = hmr.validate_hfbridge_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("query_promotion_requested:hfbridge-eval-metadata-snapshot", report["failures"])
        self.assertIn("query_promotion_admin_approval_required_not_true:hfbridge-eval-metadata-snapshot", report["failures"])


if __name__ == "__main__":
    unittest.main()
