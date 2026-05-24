#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_onboarding_ladder_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate onboarding ladder runtime behavior.
Inputs: Onboarding ladder policy, primary docs and example scenarios.
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

import onboarding_ladder_runtime as olr


class OnboardingLadderRuntimeTests(unittest.TestCase):
    def test_workspace_policy_validates(self) -> None:
        policy = olr.load_policy(ROOT / "configs" / "onboarding-ladder-policy.json")
        report = olr.validate_onboarding_ladder_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(5, report["metrics"]["ladder_steps"])
        self.assertGreaterEqual(report["metrics"]["boundary_refs"], 12)
        self.assertGreaterEqual(report["metrics"]["resolved_refs"], 20)

    def test_primary_docs_encode_ladder_shape(self) -> None:
        report = olr.analyze_onboarding_docs(
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            forbidden_primary_leads=["Canonical root (Windows lab)", "Windows lab workflow first", "Start from Windows lab"],
        )
        self.assertTrue(report["ok"], report["failures"])
        checks = report["checks"]
        self.assertTrue(checks["readme_five_minute"])
        self.assertTrue(checks["readme_links_quickstart"])
        self.assertTrue(checks["quickstart_vm_selftest"])
        self.assertTrue(checks["setup_modes_differences"])
        self.assertTrue(checks["production_after_quickstart"])
        self.assertTrue(checks["primary_docs_do_not_lead_windows_lab"])

    def test_cli_summary_is_json_and_reports_success(self) -> None:
        raw = subprocess.check_output(
            [sys.executable, str(ROOT / "src" / "onboarding_ladder_runtime.py"), "--summary"],
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        payload = json.loads(raw)
        self.assertTrue(payload["ok"], payload["failures"])
        self.assertEqual(5, payload["metrics"]["ladder_steps"])


if __name__ == "__main__":
    unittest.main()
