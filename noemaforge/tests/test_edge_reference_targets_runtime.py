#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_edge_reference_targets_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate Edge Reference Targets contracts for optional post-MVP integrations.
Inputs: Workspace Edge Reference Targets policy and temporary broken fixtures.
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

import edge_reference_targets_runtime as ertr
import production_ai_contracts as pac


class EdgeReferenceTargetsRuntimeTests(unittest.TestCase):
    def test_workspace_edge_reference_targets_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "edge-reference-targets.json"
        report = ertr.validate_edge_reference_targets_policy(
            ertr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(4, report["metrics"]["targets"])
        self.assertEqual(4, report["metrics"]["passing_targets"])
        self.assertEqual(1, report["metrics"]["orchestration_targets"])
        self.assertEqual(1, report["metrics"]["stream_rule_engine_targets"])
        self.assertEqual(2, report["metrics"]["ota_reference_targets"])
        self.assertEqual(0, report["metrics"]["first_start_required_targets"])
        self.assertEqual(0, report["metrics"]["runtime_required_targets"])
        self.assertEqual(0, report["metrics"]["missing_refs"])

        gate = pac.evaluate_gate(
            {"change_id": "edge-reference-targets-core", "domain": "pipeline"},
            ertr.edge_reference_targets_report_to_gate_evidence(report, artifact_uri="reports/edge-reference-targets.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_reference_targets_are_not_allowed_to_become_runtime_dependencies(self) -> None:
        policy_path = ROOT / "configs" / "edge-reference-targets.json"
        payload = copy.deepcopy(ertr.load_policy(policy_path))
        kubeedge = payload["targets"][0]
        kubeedge["status"] = "stable"
        kubeedge["required_for_first_start"] = True
        ekuiper = payload["targets"][1]
        ekuiper["preferred"] = False
        ekuiper["required_runtime_dependency"] = True
        mender = payload["targets"][2]
        mender["status"] = "post_mvp"

        report = ertr.validate_edge_reference_targets_policy(
            payload,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("target_status_not_allowed:kubeedge:stable", report["failures"])
        self.assertIn("target_required_for_first_start:kubeedge", report["failures"])
        self.assertIn("target_orchestration_not_post_mvp:kubeedge:stable", report["failures"])
        self.assertIn("target_ekuiper_not_preferred:ekuiper", report["failures"])
        self.assertIn("target_required_runtime_dependency:ekuiper", report["failures"])
        self.assertIn("target_ota_not_reference_only:mender:post_mvp", report["failures"])


if __name__ == "__main__":
    unittest.main()
