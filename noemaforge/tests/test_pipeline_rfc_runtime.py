#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_rfc_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate Pipeline_RFC contracts for self-development and pipeline mutation gates.
Inputs: Workspace Pipeline RFC policy and temporary broken fixtures.
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
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import pipeline_rfc_runtime as prr
import production_ai_contracts as pac


class PipelineRFCRuntimeTests(unittest.TestCase):
    def test_workspace_pipeline_rfc_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "pipeline-rfc-policy.json"
        report = prr.validate_pipeline_rfc_policy(
            prr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(2, report["metrics"]["rfcs"])
        self.assertEqual(2, report["metrics"]["passing_rfcs"])
        self.assertEqual(2, report["metrics"]["scoring_cases"])
        self.assertEqual(2, report["metrics"]["passing_scoring_cases"])

        gate = pac.evaluate_gate(
            {"change_id": "pipeline-rfc-mutation-core", "domain": "pipeline"},
            prr.pipeline_rfc_report_to_gate_evidence(report, artifact_uri="reports/pipeline-rfc.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_apply_allowed_without_approval_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "pipeline-rfc-policy.json"
        policy = prr.load_policy(policy_path)
        example_set = prr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "pipeline_rfc.example.json")
        rfc = example_set["rfcs"][1]
        rfc["status"] = "ready_to_apply"
        rfc["finalization"]["apply_allowed"] = True

        with patch.object(prr, "load_example_set", return_value=example_set):
            report = prr.validate_pipeline_rfc_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertTrue(any("rfc_apply_allowed_with_blocker:pipeline-rfc-unapproved-code-patch" in item for item in report["failures"]))
        self.assertTrue(any("rfc_explicit_approval_missing" in item for item in report["failures"]))

    def test_stage_order_and_dry_run_side_effects_are_blocked(self) -> None:
        policy_path = ROOT / "configs" / "pipeline-rfc-policy.json"
        policy = prr.load_policy(policy_path)
        example_set = prr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "pipeline_rfc.example.json")
        rfc = example_set["rfcs"][0]
        rfc["stage_order"] = ["rfc", "eval", "dry_run", "rollback", "approval", "apply"]
        rfc["dry_run"]["side_effects"] = True

        with patch.object(prr, "load_example_set", return_value=example_set):
            report = prr.validate_pipeline_rfc_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("rfc_stage_order_invalid:pipeline-rfc-safe-routing-change", report["failures"])
        self.assertTrue(any("rfc_dry_run_has_side_effects:pipeline-rfc-safe-routing-change" in item for item in report["failures"]))

    def test_build_pipeline_rfc_allows_approved_and_blocks_missing_dry_run(self) -> None:
        policy = prr.load_policy(ROOT / "configs" / "pipeline-rfc-policy.json")
        approved = prr.build_pipeline_rfc(
            "pipeline_config",
            {"files": ["noemaforge/configs/unified-registry.json"], "risk_level": "medium", "dangerous_action": False},
            {"performed": True, "side_effects": False, "artifact_ref": "prelaunch/governance/research_packet.example.json"},
            [
                {"id": "pipeline_eval", "status": "passed", "artifact_ref": "prelaunch/governance/research_packet.example.json"},
                {"id": "safety_eval", "status": "passed", "artifact_ref": "prelaunch/governance/provenance_watermark.example.json"},
                {"id": "rollback_plan", "status": "passed", "artifact_ref": "docs/backlog/ROADMAP_AND_TODO.md"},
            ],
            {"present": True, "artifact_ref": "docs/backlog/ROADMAP_AND_TODO.md", "steps": ["Restore.", "Retest."]},
            {"state": "approved", "explicit": True, "approver_role": "Admin", "approved_at": "2026-05-20T00:00:00Z"},
            policy,
        )
        self.assertEqual("ready_to_apply", approved["status"])
        self.assertTrue(approved["finalization"]["apply_allowed"])

        blocked = prr.build_pipeline_rfc(
            "pipeline_config",
            {"files": ["noemaforge/configs/unified-registry.json"], "risk_level": "medium", "dangerous_action": False},
            {"performed": False, "side_effects": False, "artifact_ref": ""},
            [],
            {"present": False, "artifact_ref": "", "steps": []},
            {"state": "not_requested", "explicit": False},
            policy,
        )
        self.assertEqual("blocked", blocked["status"])
        self.assertFalse(blocked["finalization"]["apply_allowed"])


if __name__ == "__main__":
    unittest.main()
