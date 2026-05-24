#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_artifact_card_affordance_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Admin GUI artifact-card open/download affordance runtime behavior.
Inputs: Workspace artifact-card affordance policy and temporary local artifact files.
Outputs: unittest assertions only.
Side effects: Temporary files under unittest temp directories only.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import admin_gui_server as ags
import artifact_card_affordance_runtime as acar


class ArtifactCardAffordanceRuntimeTests(unittest.TestCase):
    def test_workspace_artifact_card_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "artifact-card-affordance-policy.json"
        report = acar.validate_artifact_card_affordance_policy(
            acar.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(2, report["metrics"]["api_paths"])
        self.assertEqual(5, report["metrics"]["allowed_roots"])

    def test_artifact_open_download_are_guarded_and_enriched(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            server = acar.build_offline_artifact_server(package_root=ROOT, scratch_root=tmp)
            artifact = server.model_selection_state / "run-001" / "selection-plan.json"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text(json.dumps({"plan": "review", "ok": True}), encoding="utf-8")
            outside = tmp / "outside.json"
            outside.write_text("{}", encoding="utf-8")

            card = ags.enrich_artifact_card({"type": "model_selection_artifact", "label": "selection-plan.json", "path": str(artifact)})
            opened = server.artifact_open(str(artifact))
            downloaded = server.artifact_download_payload(str(artifact))
            blocked = server.artifact_open(str(outside))

        self.assertIn("/api/artifacts/open", card["open_url"])
        self.assertIn("/api/artifacts/download", card["download_url"])
        self.assertTrue(opened["ok"], opened)
        self.assertIn('"plan": "review"', opened["preview"])
        self.assertTrue(downloaded["ok"], downloaded)
        self.assertEqual(artifact.name, downloaded["filename"])
        self.assertFalse(blocked["ok"], blocked)
        self.assertEqual("artifact path outside allowed roots", blocked["error"])


if __name__ == "__main__":
    unittest.main()
