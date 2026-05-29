#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_setup_mode_matrix_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate setup mode matrix runtime behavior.
Inputs: Setup mode matrix policy, setup mode matrix, root setup.sh and example scenarios.
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

import setup_mode_matrix_runtime as smm


class SetupModeMatrixRuntimeTests(unittest.TestCase):
    def test_workspace_policy_validates(self) -> None:
        policy = smm.load_policy(ROOT / "configs" / "setup-mode-matrix-policy.json")
        report = smm.validate_setup_mode_matrix_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(4, report["metrics"]["modes"])
        self.assertGreaterEqual(report["metrics"]["boundary_refs"], 10)
        self.assertGreaterEqual(report["metrics"]["resolved_refs"], 18)

    def test_mode_matrix_encodes_host_vm_macos_and_docker_boundaries(self) -> None:
        matrix = smm.load_mode_matrix(ROOT / "configs" / "setup-modes.json")
        report = smm.validate_mode_matrix(matrix)
        self.assertTrue(report["ok"], report["failures"])
        modes = matrix["modes"]
        self.assertTrue(modes["host"]["production_runtime_path"])
        self.assertTrue(modes["host"]["requires_root_for_apply"])
        self.assertIn("Native services", modes["host"]["purpose"])
        self.assertTrue(modes["vm"]["recommended_first_success"])
        self.assertTrue(modes["vm"]["dry_run_default"])
        self.assertFalse(modes["macos-dev"]["writes_privileged_system_files"])
        self.assertFalse(modes["docker-dev"]["production_runtime_path"])
        self.assertIn("not the full production", modes["docker-dev"]["purpose"])

    def test_cli_summary_is_json_and_reports_success(self) -> None:
        raw = subprocess.check_output(
            [sys.executable, str(ROOT / "src" / "setup_mode_matrix_runtime.py"), "--summary"],
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        payload = json.loads(raw)
        self.assertTrue(payload["ok"], payload["failures"])
        self.assertEqual(4, payload["metrics"]["modes"])


if __name__ == "__main__":
    unittest.main()
