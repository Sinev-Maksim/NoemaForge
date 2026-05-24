#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_ota_update_layer_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate OTA Update Layer contracts for staged rollout, rollback and health gates.
Inputs: Workspace OTA policy, update manifest and local update-agent skeleton.
Outputs: unittest assertions only.
Side effects: Creates and removes a temporary broken manifest fixture.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
TMP_ROOT = ROOT / "tests" / "_tou"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

import ota_update_layer_runtime as oalr
import production_ai_contracts as pac
from ota import update_agent


class OTAUpdateLayerRuntimeTests(unittest.TestCase):
    def tearDown(self) -> None:
        if TMP_ROOT.exists():
            shutil.rmtree(TMP_ROOT)

    def test_workspace_ota_update_layer_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "ota-update-layer.json"
        report = oalr.validate_ota_update_layer_policy(
            oalr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["update_manifests"])
        self.assertEqual(1, report["metrics"]["passing_update_manifests"])
        self.assertEqual(1, report["metrics"]["staged_rollouts"])
        self.assertEqual(1, report["metrics"]["rollback_enabled"])
        self.assertEqual(1, report["metrics"]["health_gates_passed"])
        self.assertEqual(0, report["metrics"]["missing_refs"])

        gate = pac.evaluate_gate(
            {"change_id": "ota-update-layer-core", "domain": "pipeline"},
            oalr.ota_update_layer_report_to_gate_evidence(report, artifact_uri="reports/ota-update-layer.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_update_agent_plans_activation_only_after_health_gate(self) -> None:
        manifest = json.loads((PROJECT_ROOT / "prelaunch" / "ota" / "update_manifest.json").read_text(encoding="utf-8"))
        plan = update_agent.plan_update(manifest)

        self.assertTrue(plan["staged_rollout"])
        self.assertTrue(plan["health_gate_passed"])
        self.assertTrue(plan["activation_allowed"])
        self.assertTrue(plan["rollback"]["ok"])
        self.assertEqual("edge-gateway-bundle-0.31.13-alpha-patched1", plan["rollback"]["previous_bundle_id"])

    def test_rollout_rollback_and_health_gate_are_enforced(self) -> None:
        policy_path = ROOT / "configs" / "ota-update-layer.json"
        payload = copy.deepcopy(oalr.load_policy(policy_path))
        manifest = json.loads((PROJECT_ROOT / "prelaunch" / "ota" / "update_manifest.json").read_text(encoding="utf-8"))
        manifest["staged_rollout"]["enabled"] = False
        manifest["previous_bundle"]["id"] = ""
        manifest["rollback"]["enabled"] = False
        manifest["health_gate"]["status"] = "failed"
        manifest["health_gate"]["checks"][1]["status"] = "failed"
        manifest["activation"]["requires_health_gate"] = False
        manifest["activation"]["activated"] = True
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        broken = TMP_ROOT / "broken_update_manifest.json"
        broken.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        payload["update_manifests"] = [{"id": "broken-update", "ref": "tests/_tou/broken_update_manifest.json"}]

        report = oalr.validate_ota_update_layer_policy(
            payload,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("ota_staged_rollout_not_enabled:edge-gateway-shadow-update", report["failures"])
        self.assertIn("ota_previous_bundle_missing:edge-gateway-shadow-update", report["failures"])
        self.assertIn("ota_rollback_not_enabled:edge-gateway-shadow-update", report["failures"])
        self.assertIn("ota_health_gate_not_passed:edge-gateway-shadow-update", report["failures"])
        self.assertIn("ota_health_gate_check_not_passed:edge-gateway-shadow-update:ready", report["failures"])
        self.assertIn("ota_activation_without_health_gate:edge-gateway-shadow-update", report["failures"])
        self.assertIn("ota_activated_without_passed_health_gate:edge-gateway-shadow-update", report["failures"])


if __name__ == "__main__":
    unittest.main()
