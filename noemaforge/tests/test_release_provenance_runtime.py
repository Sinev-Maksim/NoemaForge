#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_release_provenance_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate signed release provenance archive invariants.
Inputs: Workspace release provenance policy and offline release provenance fixtures.
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
import release_provenance_runtime as rpr


class ReleaseProvenanceRuntimeTests(unittest.TestCase):
    def test_workspace_release_provenance_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "release-provenance-policy.json"
        report = rpr.validate_release_provenance_policy(
            rpr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["releases"])
        self.assertEqual(1, report["metrics"]["passing_releases"])
        self.assertEqual(2, report["metrics"]["signed_artifacts"])
        self.assertEqual(8, report["metrics"]["required_materials"])

        gate = pac.evaluate_gate(
            {"change_id": "release-provenance-core", "domain": "pipeline"},
            rpr.release_provenance_report_to_gate_evidence(report, artifact_uri="reports/release-provenance.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_archive_record_hashes_existing_file_without_writing(self) -> None:
        policy_path = ROOT / "configs" / "release-provenance-policy.json"
        record = rpr.build_release_archive_record(policy_path)

        self.assertEqual("release_archive", record["kind"])
        self.assertEqual(policy_path.name, record["path"])
        self.assertRegex(record["sha256"], r"^[a-f0-9]{64}$")
        self.assertGreater(record["bytes"], 0)

    def test_missing_detached_signature_breaks_contract(self) -> None:
        policy_path = ROOT / "configs" / "release-provenance-policy.json"
        policy = rpr.load_policy(policy_path)
        example = rpr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "release_provenance.example.json")
        broken = copy.deepcopy(example)
        broken["releases"][0]["signatures"] = []

        with patch.object(rpr, "load_example_set", return_value=broken):
            report = rpr.validate_release_provenance_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertFalse(report["ok"])
        self.assertIn("release_signature_missing:noemaforge-0.32.1-alpha-patched1-public-archive", report["failures"])
        self.assertIn("release_signature_artifact_missing:noemaforge-0.32.1-alpha-patched1-public-archive:archive", report["failures"])

    def test_install_transcript_and_verification_summary_are_required(self) -> None:
        policy_path = ROOT / "configs" / "release-provenance-policy.json"
        policy = rpr.load_policy(policy_path)
        example = rpr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "release_provenance.example.json")
        broken = copy.deepcopy(example)
        del broken["releases"][0]["materials"]["install_transcript"]
        broken["releases"][0]["materials"]["verification_summary"]["status"] = "failed"

        with patch.object(rpr, "load_example_set", return_value=broken):
            report = rpr.validate_release_provenance_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertFalse(report["ok"])
        self.assertIn("release_material_missing:noemaforge-0.32.1-alpha-patched1-public-archive:install_transcript", report["failures"])
        self.assertIn("release_verification_summary_not_passed:noemaforge-0.32.1-alpha-patched1-public-archive", report["failures"])


if __name__ == "__main__":
    unittest.main()
