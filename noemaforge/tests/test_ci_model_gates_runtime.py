#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_ci_model_gates_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate offline CI model gates for latency, memory, replay, schema and signature evidence.
Inputs: Workspace CI model gates policy and temporary broken fixtures.
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

import ci_model_gates_runtime as cmgr
import production_ai_contracts as pac


class CIModelGatesRuntimeTests(unittest.TestCase):
    def test_workspace_ci_model_gates_validate_release_evidence(self) -> None:
        policy_path = ROOT / "configs" / "ci-model-gates.json"
        report = cmgr.validate_ci_model_gates(
            cmgr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["gates"])
        self.assertEqual(1, report["metrics"]["edge_gates"])
        self.assertEqual(1, report["metrics"]["passing_gates"])
        self.assertEqual(0, report["metrics"]["missing_refs"])
        self.assertLessEqual(report["metrics"]["max_observed_p95_latency_ms"], 50.0)
        self.assertLessEqual(report["metrics"]["max_observed_peak_memory_mb"], 128.0)

        gate = pac.evaluate_gate(
            {"change_id": "ci-model-gates-core", "domain": "model"},
            cmgr.ci_model_gates_report_to_gate_evidence(report, artifact_uri="reports/ci-model-gates.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_ci_model_gates_block_budget_schema_signature_and_replay_regressions(self) -> None:
        policy_path = ROOT / "configs" / "ci-model-gates.json"
        payload = copy.deepcopy(cmgr.load_policy(policy_path))
        evidence = payload["gates"][0]["release_evidence"]["checks"]
        by_id = {item["id"]: item for item in evidence}
        by_id["latency"]["p95_latency_ms"] = 99.0
        by_id["memory"]["peak_memory_mb"] = 256.0
        by_id["schema_compatibility"]["compatible"] = False
        by_id["signature"]["verified"] = False
        by_id["golden_replay"]["cases_passed"] = 2

        report = cmgr.validate_ci_model_gates(
            payload,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("gate_latency_budget_exceeded:edge-model-ci-gate", report["failures"])
        self.assertIn("gate_memory_budget_exceeded:edge-model-ci-gate", report["failures"])
        self.assertIn("gate_schema_not_compatible:edge-model-ci-gate", report["failures"])
        self.assertIn("gate_signature_not_verified:edge-model-ci-gate", report["failures"])
        self.assertIn("gate_golden_replay_not_complete:edge-model-ci-gate", report["failures"])

    def test_ci_model_gates_require_release_evidence_ref(self) -> None:
        policy_path = ROOT / "configs" / "ci-model-gates.json"
        payload = copy.deepcopy(cmgr.load_policy(policy_path))
        payload["gates"][0]["release_evidence_ref"] = "prelaunch/evidence/ci-model-gates/missing/release_evidence.json"
        payload["gates"][0]["refs"] = []

        report = cmgr.validate_ci_model_gates(
            payload,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn(
            "missing_ref:edge-model-ci-gate:prelaunch/evidence/ci-model-gates/missing/release_evidence.json",
            report["failures"],
        )


if __name__ == "__main__":
    unittest.main()
