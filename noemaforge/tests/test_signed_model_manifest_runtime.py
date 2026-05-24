#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_signed_model_manifest_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate signed model manifests for signatures, budgets and independent QA blocking.
Inputs: Workspace signed model manifest policy and temporary broken fixtures.
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

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import production_ai_contracts as pac
import signed_model_manifest_runtime as smmr


class SignedModelManifestRuntimeTests(unittest.TestCase):
    def test_workspace_signed_model_manifest_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "signed-model-manifest-policy.json"
        report = smmr.validate_signed_model_manifest_policy(
            smmr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["manifests"])
        self.assertEqual(1, report["metrics"]["passing_manifests"])
        self.assertEqual(1, report["metrics"]["signed_manifests"])
        self.assertEqual(1, report["metrics"]["sha256_manifests"])
        self.assertEqual(1, report["metrics"]["budgeted_manifests"])
        self.assertEqual(1, report["metrics"]["qa_blocker_ready_manifests"])
        self.assertEqual(0, report["metrics"]["missing_refs"])

        gate = pac.evaluate_gate(
            {"change_id": "signed-model-manifest-core", "domain": "model"},
            smmr.signed_model_manifest_report_to_gate_evidence(report, artifact_uri="reports/signed-model-manifest.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_manifest_contract_rejects_unsigned_unbudgeted_or_qa_dependent_model(self) -> None:
        policy_path = ROOT / "configs" / "signed-model-manifest-policy.json"
        policy = smmr.load_policy(policy_path)
        manifest = smmr.load_manifest(PROJECT_ROOT / "prelaunch" / "manifests" / "models" / "example_edge_model.manifest.json")
        broken = copy.deepcopy(manifest)
        broken["sha256"] = ""
        broken["signature"] = ""
        broken["budgets"]["latency_budget_ms"] = 0
        broken["fallback"] = "previous_model"
        broken["qa_gate"]["reviewer_role"] = "developer"
        broken["qa_gate"]["independent_from_developer"] = False
        broken["qa_gate"]["can_block_release"] = False
        broken["qa_gate"]["status"] = "pending"

        failures = smmr._manifest_failures(broken, policy["policy"])

        self.assertIn("manifest_sha256_invalid:example-edge-model", failures)
        self.assertIn("manifest_signature_missing:example-edge-model", failures)
        self.assertIn("manifest_latency_budget_invalid:example-edge-model", failures)
        self.assertIn("manifest_edge_fallback_not_whitebox:example-edge-model", failures)
        self.assertIn("manifest_qa_reviewer_not_qa:example-edge-model", failures)
        self.assertIn("manifest_qa_independent_flag_missing:example-edge-model", failures)
        self.assertIn("manifest_qa_cannot_block_release:example-edge-model", failures)
        self.assertIn("manifest_deployable_without_qa_approval:example-edge-model:pending", failures)

    def test_policy_blocks_missing_manifest_ref(self) -> None:
        policy_path = ROOT / "configs" / "signed-model-manifest-policy.json"
        payload = copy.deepcopy(smmr.load_policy(policy_path))
        payload["manifest_refs"][0]["ref"] = "prelaunch/manifests/models/missing.manifest.json"

        report = smmr.validate_signed_model_manifest_policy(
            payload,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("missing_ref:example-edge-model:prelaunch/manifests/models/missing.manifest.json", report["failures"])


if __name__ == "__main__":
    unittest.main()
