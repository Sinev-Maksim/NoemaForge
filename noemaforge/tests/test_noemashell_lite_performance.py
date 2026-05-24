#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_noemashell_lite_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test NoemaShell Lite validation on synthetic session catalogs.
Inputs: Workspace policy expanded with hundreds of NoemaShellLiteSession records.
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
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import noemashell_lite_runtime as nslr


class NoemaShellLitePerformanceTests(unittest.TestCase):
    def test_synthetic_noemashell_session_catalog_validates_under_budget(self) -> None:
        policy = nslr.load_policy(ROOT / "configs" / "noemashell-lite-policy.json")
        base_set = nslr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "noemashell_lite.example.json")
        synthetic_set = copy.deepcopy(base_set)
        base_session = copy.deepcopy(base_set["sessions"][0])
        synthetic_set["sessions"] = []
        for index in range(300):
            session = copy.deepcopy(base_session)
            session["id"] = f"{session['id']}-{index:03d}"
            session["trace_id"] = f"{session['trace_id']}:{index:03d}"
            session["surfaces"]["approvals"][0]["id"] = f"approval:repair-session:{index:03d}"
            session["surfaces"]["approvals"][0]["trace_id"] = f"trace:noemashell:approval:repair-session:{index:03d}"
            synthetic_set["sessions"].append(session)

        started = time.perf_counter()
        with patch.object(nslr, "load_example_set", return_value=synthetic_set):
            report = nslr.validate_noemashell_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["sessions"])
        self.assertEqual(300, report["metrics"]["passing_sessions"])
        self.assertEqual(6, report["metrics"]["required_surfaces"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
