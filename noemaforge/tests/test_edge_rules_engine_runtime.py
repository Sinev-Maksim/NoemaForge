#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_edge_rules_engine_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate Edge Rules Engine contracts for guarded ML score and whitebox fallback.
Inputs: Workspace Edge Rules Engine policy and temporary broken fixtures.
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

import edge_rules_engine_runtime as erer
import production_ai_contracts as pac


class EdgeRulesEngineRuntimeTests(unittest.TestCase):
    def test_workspace_edge_rules_engine_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "edge-rules-engine-policy.json"
        report = erer.validate_edge_rules_engine_policy(
            erer.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(2, report["metrics"]["rules"])
        self.assertEqual(1, report["metrics"]["whitebox_only_rules"])
        self.assertEqual(1, report["metrics"]["guarded_ml_rules"])
        self.assertGreaterEqual(report["metrics"]["thresholds"], 4)
        self.assertEqual(0, report["metrics"]["missing_refs"])

        gate = pac.evaluate_gate(
            {"change_id": "edge-rules-engine-core", "domain": "pipeline"},
            erer.edge_rules_report_to_gate_evidence(report, artifact_uri="reports/edge-rules-engine.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_ml_score_is_blocked_without_pre_and_post_rule_guards(self) -> None:
        policy_path = ROOT / "configs" / "edge-rules-engine-policy.json"
        payload = copy.deepcopy(erer.load_policy(policy_path))
        rule = payload["rules"][1]
        rule["applies_before_ml"] = False
        rule["applies_after_ml"] = False
        rule["thresholds"] = [
            {"metric": "temperature_c", "op": "gte", "value": 70.0, "action": "allow"}
        ]
        rule["anomaly_route"]["enabled"] = False
        rule["drift_flags"]["metrics"] = []

        report = erer.validate_edge_rules_engine_policy(
            payload,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("rule_ml_score_without_pre_guard:guarded-ml-score-postcheck", report["failures"])
        self.assertIn("rule_ml_score_without_post_guard:guarded-ml-score-postcheck", report["failures"])
        self.assertIn("rule_ml_score_threshold_missing:guarded-ml-score-postcheck", report["failures"])
        self.assertIn("rule_anomaly_route_not_enabled:guarded-ml-score-postcheck", report["failures"])
        self.assertIn("rule_drift_metrics_empty:guarded-ml-score-postcheck", report["failures"])

    def test_signed_manifest_ref_is_required_and_resolved(self) -> None:
        policy_path = ROOT / "configs" / "edge-rules-engine-policy.json"
        payload = copy.deepcopy(erer.load_policy(policy_path))
        payload["rules"][0]["signed_model_manifest_ref"] = "prelaunch/manifests/models/missing.manifest.json"
        payload["rules"][0]["refs"] = ["prelaunch/rules/edge/fallback_rules.json"]

        report = erer.validate_edge_rules_engine_policy(
            payload,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn(
            "missing_ref:whitebox-temperature-fallback:prelaunch/manifests/models/missing.manifest.json",
            report["failures"],
        )


if __name__ == "__main__":
    unittest.main()
