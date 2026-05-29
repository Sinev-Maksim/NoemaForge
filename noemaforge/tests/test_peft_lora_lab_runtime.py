#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_peft_lora_lab_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate disabled PEFT/LoRA lab readiness gates and EvaluationGate evidence.
Inputs: Workspace PEFT/LoRA lab policy and temporary broken fixtures.
Outputs: unittest assertions only.
Side effects: Creates and removes temporary fixture directories.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import peft_lora_lab_runtime as pllr
import production_ai_contracts as pac


class PEFTLoRALabRuntimeTests(unittest.TestCase):
    def test_workspace_peft_lora_lab_policy_validates_disabled_readiness(self) -> None:
        policy_path = ROOT / "configs" / "peft-lora-lab-policy.json"
        report = pllr.validate_peft_lora_lab_policy(
            pllr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["labs"])
        self.assertEqual(1, report["metrics"]["disabled_labs"])
        self.assertEqual(0, report["metrics"]["active_labs"])
        self.assertEqual(0, report["metrics"]["training_enabled_labs"])
        self.assertEqual(0, report["metrics"]["production_weight_write_labs"])
        self.assertEqual(0, report["metrics"]["missing_refs"])

        gate = pac.evaluate_gate(
            {"change_id": "peft-lora-lab-readiness", "domain": "model"},
            pllr.peft_lora_report_to_gate_evidence(report, artifact_uri="reports/peft-lora-lab.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_policy_blocks_training_and_weight_mutation_shortcuts(self) -> None:
        policy_path = ROOT / "configs" / "peft-lora-lab-policy.json"
        payload = copy.deepcopy(pllr.load_policy(policy_path))
        payload["policy"]["training_enabled"] = True
        payload["labs"][0]["state"] = "enabled"
        payload["labs"][0]["training_plan"]["enabled"] = True
        payload["labs"][0]["training_plan"]["writes_production_weights"] = True
        payload["labs"][0]["dataset_manifest"]["approved_for_training"] = True
        payload["labs"][0]["release_evidence"]["evidence_ref"] = ""

        report = pllr.validate_peft_lora_lab_policy(
            payload,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("policy_training_enabled_not_false", report["failures"])
        self.assertIn("lab_training_enabled:dev-code-lora-dry-run", report["failures"])
        self.assertIn("lab_writes_production_weights:dev-code-lora-dry-run", report["failures"])
        self.assertIn("lab_dataset_approved_for_training:dev-code-lora-dry-run", report["failures"])
        self.assertIn("lab_active_without_release_evidence:dev-code-lora-dry-run", report["failures"])

    def test_validation_blocks_missing_dataset_ref(self) -> None:
        policy_path = ROOT / "configs" / "peft-lora-lab-policy.json"
        payload = copy.deepcopy(pllr.load_policy(policy_path))
        payload["labs"][0]["dataset_manifest"]["dataset_ref"] = "datasets/role_eval_cases/missing.jsonl"

        report = pllr.validate_peft_lora_lab_policy(
            payload,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("missing_ref:dev-code-lora-dry-run:datasets/role_eval_cases/missing.jsonl", report["failures"])
        self.assertEqual(1, report["metrics"]["missing_refs"])


if __name__ == "__main__":
    unittest.main()
