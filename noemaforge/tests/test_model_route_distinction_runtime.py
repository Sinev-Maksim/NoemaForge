#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_model_route_distinction_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Model Selection vs Model Evolution routing and GUI semantic boundaries.
Inputs: Workspace model-route-distinction policy plus Admin runtime and GUI source.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import admin_runtime
import model_route_distinction_runtime as mrdr


class ModelRouteDistinctionRuntimeTests(unittest.TestCase):
    def test_workspace_model_route_distinction_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "model-route-distinction-policy.json"
        report = mrdr.validate_model_route_distinction_policy(
            mrdr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(report["metrics"]["route_samples"], report["metrics"]["valid_route_samples"])
        self.assertGreater(report["metrics"]["selection_block_chars"], 100)
        self.assertGreater(report["metrics"]["evolution_block_chars"], 100)

    def test_router_sends_selection_and_evolution_to_different_modes(self) -> None:
        selection = admin_runtime.route_request("оптимизируй модель для dev team normal")
        evolution = admin_runtime.route_request("проведи эволюцию модели для ревью кода")

        self.assertEqual("model_selection", selection["id"])
        self.assertEqual("model_selection", selection["intent"])
        self.assertEqual("model_selection_plan", selection["execute_mode"])
        self.assertEqual("model_evolution", evolution["id"])
        self.assertEqual("model_evolution", evolution["intent"])
        self.assertEqual("pipeline_and_model_evolution", evolution["execute_mode"])
        self.assertNotEqual(selection["execute_mode"], evolution["execute_mode"])

    def test_gui_copy_and_personas_keep_visual_distinction(self) -> None:
        policy = mrdr.load_policy(ROOT / "configs" / "model-route-distinction-policy.json")
        report = mrdr.validate_model_route_distinction_policy(
            policy,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            include_docs=False,
        )

        route = report["route"]
        self.assertEqual("Runtime model selection / epoch optimization", route["selection_route"]["label"])
        self.assertEqual("Model evolution / measured improvement cycle", route["evolution_route"]["label"])
        self.assertIn("Optimizer", (ROOT / "templates" / "pipeline-dashboard" / "app.js").read_text(encoding="utf-8"))
        self.assertIn("Model Evolution", (ROOT / "templates" / "pipeline-dashboard" / "app.js").read_text(encoding="utf-8"))
        self.assertTrue(report["ok"], report["failures"])


if __name__ == "__main__":
    unittest.main()
