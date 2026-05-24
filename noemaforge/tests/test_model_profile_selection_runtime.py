#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_model_profile_selection_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate model profile selection manifests and workspace policy.
Inputs: Model Profile Selection policy and model profile manifests.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import model_profile_selection_runtime as mps
import model_profiles


class ModelProfileSelectionRuntimeTests(unittest.TestCase):
    def test_workspace_policy_validates(self) -> None:
        policy = mps.load_policy(ROOT / "configs" / "model-profile-selection-policy.json")
        report = mps.validate_model_profile_selection_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(5, report["metrics"]["profiles"])
        self.assertEqual(len(policy["refs"]), report["metrics"]["resolved_refs"])

    def test_each_profile_manifest_is_no_download_and_single_active(self) -> None:
        profiles = model_profiles.load_profiles(ROOT)
        validation = model_profiles.validate_profiles(profiles)
        self.assertTrue(validation["ok"], validation["failures"])
        for name in mps.REQUIRED_PROFILES:
            manifest = model_profiles.build_profile_manifest(profiles, name)
            self.assertEqual(name, manifest["profile"])
            self.assertEqual(1, manifest["runtime"]["max_active_llms"])
            self.assertFalse(manifest["runtime"]["heavy_llm_autostart"])
            self.assertTrue(manifest["stage_roles"])
            self.assertTrue(manifest["fetch_candidates"])
            self.assertTrue(all(item["auto_download"] is False for item in manifest["fetch_candidates"]))

    def test_cli_plan_outputs_manifest_json(self) -> None:
        raw = subprocess.check_output(
            [sys.executable, str(ROOT / "src" / "model_profiles.py"), "plan", "writer", "--root", str(ROOT), "--json"],
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        manifest = json.loads(raw)
        self.assertEqual("ModelProfileManifest", manifest["kind"])
        self.assertEqual("writer", manifest["profile"])
        self.assertIn("writer", ",".join(manifest["stage_roles"]))
        self.assertTrue(all(item["auto_download"] is False for item in manifest["fetch_candidates"]))


if __name__ == "__main__":
    unittest.main()
