#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_previous_install_context_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate previous-install context cannot become active runtime.
Inputs: Synthetic runtime contexts and previous install context policy.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import previous_install_context_runtime as pic
import production_ai_contracts as pac


def valid_context() -> dict:
    return {
        "apiVersion": "noemaforge.previous-install-context/v1",
        "kind": "PreviousInstallContextExample",
        "active_runtime": {
            "install_root": "/opt/noemaforge",
            "state_root": "/var/lib/noemaforge",
            "share_root": "/mnt/noemaforge-share",
            "modelstore_root": "/var/lib/modelstore",
            "bootstrap_state_dir": "/var/lib/noemaforge/bootstrap",
        },
        "previous_install": {
            "path": "/var/lib/noemaforge/firstboot-attempt-archive/2026-05-20T000000Z",
            "mode": "archive_only",
            "active": False,
        },
        "backup": {
            "path": "/var/backups/noemaforge/prelaunch-0.32.1",
            "mode": "readonly_evidence",
            "active": False,
        },
        "migration": {
            "path": "/var/lib/noemaforge/migration-records/legacy-share-normalization.json",
            "mode": "migrate_once_then_detach",
            "active": False,
        },
    }


class PreviousInstallContextRuntimeTests(unittest.TestCase):
    def test_policy_validates_and_maps_to_pipeline_gate_evidence(self) -> None:
        policy = pic.load_policy(ROOT / "configs" / "previous-install-context-policy.json")
        report = pic.validate_previous_install_context_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertTrue(report["ok"], report["failures"])
        gate = pac.evaluate_gate(
            {
                "change_id": "previous-install-context-core",
                "domain": "pipeline",
                "required_checks": ["pipeline_eval", "rollback_plan"],
            },
            {
                "artifact_uri": "reports/previous-install-context.json",
                "run_at": "2026-05-20T00:00:00Z",
                "checks": [
                    {"id": "pipeline_eval", "status": "passed" if report["ok"] else "failed"},
                    {"id": "rollback_plan", "status": "passed"},
                ],
            },
        )
        self.assertTrue(gate["ok"], gate)

    def test_archive_only_previous_install_context_passes(self) -> None:
        policy = pic.load_policy(ROOT / "configs" / "previous-install-context-policy.json")
        report = pic.validate_previous_install_context(valid_context(), policy=policy)

        self.assertTrue(report["ok"], json.dumps(report, indent=2))
        self.assertEqual(5, report["metrics"]["active_path_count"])
        self.assertEqual(3, report["metrics"]["archive_context_count"])

    def test_backup_path_cannot_be_active_runtime_root(self) -> None:
        policy = pic.load_policy(ROOT / "configs" / "previous-install-context-policy.json")
        context = copy.deepcopy(valid_context())
        context["active_runtime"]["state_root"] = "/var/backups/noemaforge/prelaunch-0.32.1/state"
        report = pic.validate_previous_install_context(context, policy=policy)

        self.assertFalse(report["ok"])
        self.assertIn("active_path_uses_archive_fragment:state_root:backup", report["failures"])
        self.assertIn("active_path_overlaps_archive_context:state_root", report["failures"])

    def test_legacy_share_path_cannot_be_active_runtime_share(self) -> None:
        policy = pic.load_policy(ROOT / "configs" / "previous-install-context-policy.json")
        context = copy.deepcopy(valid_context())
        context["active_runtime"]["share_root"] = "/mnt/brainos-share"
        report = pic.validate_previous_install_context(context, policy=policy)

        self.assertFalse(report["ok"])
        self.assertIn("active_path_uses_legacy_prefix:share_root:/mnt/brainos-share", report["failures"])
        self.assertIn("active_path_not_under_canonical_root:share_root:/mnt/noemaforge-share", report["failures"])

    def test_archive_context_marked_active_fails(self) -> None:
        policy = pic.load_policy(ROOT / "configs" / "previous-install-context-policy.json")
        context = copy.deepcopy(valid_context())
        context["previous_install"]["active"] = True
        report = pic.validate_previous_install_context(context, policy=policy)

        self.assertFalse(report["ok"])
        self.assertIn("archive_context_marked_active:previous_install", report["failures"])


if __name__ == "__main__":
    unittest.main()
