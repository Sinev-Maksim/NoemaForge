#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_tinyml_node_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate TinyML Node contracts for MCU inference readiness.
Inputs: Workspace TinyML Node policy and temporary broken fixtures.
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
import tinyml_node_runtime as tnr


class TinyMLNodeRuntimeTests(unittest.TestCase):
    def test_workspace_tinyml_node_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "tinyml-node-policy.json"
        report = tnr.validate_tinyml_node_policy(
            tnr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["nodes"])
        self.assertEqual(1, report["metrics"]["passing_nodes"])
        self.assertEqual(0, report["metrics"]["direct_control_decision_nodes"])
        self.assertEqual(0, report["metrics"]["missing_refs"])
        self.assertLessEqual(report["metrics"]["max_observed_latency_ms"], 20.0)
        self.assertLessEqual(report["metrics"]["max_observed_ram_arena_bytes"], 65536)
        self.assertLessEqual(report["metrics"]["max_observed_model_size_bytes"], 262144)

        checks = {item["id"]: item["status"] for item in report["checks"]}
        self.assertEqual("passed", checks["golden_vectors"])
        self.assertEqual("passed", checks["latency_budget"])
        self.assertEqual("passed", checks["ram_arena_budget"])
        self.assertEqual("passed", checks["model_hash"])
        self.assertEqual("passed", checks["fallback_rules"])

        gate = pac.evaluate_gate(
            {"change_id": "tinyml-node-core", "domain": "model"},
            tnr.tinyml_node_report_to_gate_evidence(report, artifact_uri="reports/tinyml-node.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_budgets_hash_vectors_and_direct_control_are_enforced(self) -> None:
        policy_path = ROOT / "configs" / "tinyml-node-policy.json"
        payload = copy.deepcopy(tnr.load_policy(policy_path))
        node = payload["nodes"][0]
        node["golden_vectors_ref"] = "prelaunch/tinyml/golden_vectors/missing.jsonl"
        node["model_hash"] = "not-a-sha256"
        node["observed_latency_ms"] = 99.0
        node["observed_ram_arena_bytes"] = 65537
        node["observed_model_size_bytes"] = 262145
        node["direct_control_decisions"] = True
        node["fallback_rules_required"] = False

        report = tnr.validate_tinyml_node_policy(
            payload,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("node_golden_vectors_missing:example-mcu-floor-controller:prelaunch/tinyml/golden_vectors/missing.jsonl", report["failures"])
        self.assertIn("node_model_hash_invalid:example-mcu-floor-controller", report["failures"])
        self.assertIn("node_latency_budget_exceeded:example-mcu-floor-controller", report["failures"])
        self.assertIn("node_ram_arena_budget_exceeded:example-mcu-floor-controller", report["failures"])
        self.assertIn("node_model_size_budget_exceeded:example-mcu-floor-controller", report["failures"])
        self.assertIn("node_direct_control_decision_enabled:example-mcu-floor-controller", report["failures"])
        self.assertIn("node_fallback_rules_not_required:example-mcu-floor-controller", report["failures"])


if __name__ == "__main__":
    unittest.main()
