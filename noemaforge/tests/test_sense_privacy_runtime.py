#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_sense_privacy_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate Sense_State and Privacy_Filter contracts before persistence/export.
Inputs: Workspace Sense Privacy policy and temporary broken fixtures.
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
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import production_ai_contracts as pac
import sense_privacy_runtime as spr


class SensePrivacyRuntimeTests(unittest.TestCase):
    def test_workspace_sense_privacy_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "sense-privacy-policy.json"
        report = spr.validate_sense_privacy_policy(
            spr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["states"])
        self.assertEqual(1, report["metrics"]["passing_states"])
        self.assertEqual(1, report["metrics"]["filter_cases"])
        self.assertEqual(1, report["metrics"]["passing_filter_cases"])
        self.assertGreaterEqual(report["metrics"]["redactions"], 5)
        self.assertEqual(0, report["metrics"]["missing_refs"])

        gate = pac.evaluate_gate(
            {"change_id": "sense-privacy-governance-core", "domain": "pipeline"},
            spr.sense_privacy_report_to_gate_evidence(report, artifact_uri="reports/sense-privacy.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_privacy_filter_removes_sensitive_fields_and_path_values(self) -> None:
        policy = spr.load_policy(ROOT / "configs" / "sense-privacy-policy.json")["policy"]
        raw = {
            "cpu": {"usage_percent": 20},
            "username": "alice",
            "cmdline": "python C:\\Users\\alice\\tool.py",
            "nested": {"safe": "ok", "path": "/home/alice/file.txt"},
        }

        filtered = spr.apply_privacy_filter(raw, policy)

        self.assertNotIn("username", filtered["filtered"])
        self.assertNotIn("cmdline", filtered["filtered"])
        self.assertNotIn("path", filtered["filtered"]["nested"])
        self.assertGreaterEqual(len(filtered["redactions"]), 3)

    def test_raw_process_metadata_and_missing_privacy_flags_are_blocked(self) -> None:
        policy_path = ROOT / "configs" / "sense-privacy-policy.json"
        policy = spr.load_policy(policy_path)
        example_set = spr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "sense_privacy.example.json")
        state = example_set["states"][0]
        state["privacy"]["filtered"] = False
        state["privacy"]["raw_paths_stored"] = True
        state["metrics"]["process"] = {"process_name": "python.exe", "cmdline": "python secret.py"}
        state["metrics"]["cpu"]["usage_percent"] = 101.0

        with patch.object(spr, "load_example_set", return_value=example_set):
            report = spr.validate_sense_privacy_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("state_privacy_not_filtered:sense-state-coarse-host-ok", report["failures"])
        self.assertIn("state_raw_paths_stored:sense-state-coarse-host-ok", report["failures"])
        self.assertIn("state_metric_group_not_allowed:sense-state-coarse-host-ok:process", report["failures"])
        self.assertIn("state_raw_metadata_key_present:sense-state-coarse-host-ok:metrics.process.process_name", report["failures"])
        self.assertIn("state_raw_metadata_key_present:sense-state-coarse-host-ok:metrics.process.cmdline", report["failures"])
        self.assertIn("state_percent_out_of_range:sense-state-coarse-host-ok:cpu:usage_percent:101.0", report["failures"])

    def test_required_coarse_metric_groups_are_enforced(self) -> None:
        policy_path = ROOT / "configs" / "sense-privacy-policy.json"
        policy = spr.load_policy(policy_path)
        example_set = spr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "sense_privacy.example.json")
        state = example_set["states"][0]
        del state["metrics"]["network"]

        with patch.object(spr, "load_example_set", return_value=example_set):
            report = spr.validate_sense_privacy_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("state_required_metric_group_missing:sense-state-coarse-host-ok:network", report["failures"])


if __name__ == "__main__":
    unittest.main()
