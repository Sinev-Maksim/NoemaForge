#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_alpha_backlog_fence_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate alpha backlog-only fences and promotion blockers.
Inputs: Workspace Alpha Backlog Fence policy and temporary broken fixtures.
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

import alpha_backlog_fence_runtime as abfr
import production_ai_contracts as pac
import unified_registry_runtime as urr


class AlphaBacklogFenceRuntimeTests(unittest.TestCase):
    def test_workspace_alpha_backlog_fence_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "alpha-backlog-fence.json"
        report = abfr.validate_alpha_backlog_fence_policy(
            abfr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(1, report["metrics"]["fences"])
        self.assertEqual(1, report["metrics"]["passing_fences"])
        self.assertEqual(1, report["metrics"]["protected_refs"])
        self.assertEqual(4, report["metrics"]["required_gate_refs"])

        gate = pac.evaluate_gate(
            {"change_id": "alpha-backlog-fence-core", "domain": "pipeline"},
            abfr.alpha_backlog_fence_report_to_gate_evidence(report, artifact_uri="reports/alpha-backlog-fence.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_promoted_protected_registry_ref_is_blocked(self) -> None:
        policy_path = ROOT / "configs" / "alpha-backlog-fence.json"
        policy = abfr.load_policy(policy_path)
        registry = urr.load_registry(ROOT / "configs" / "unified-registry.json")
        broken_registry = copy.deepcopy(registry)
        for entry in broken_registry["entries"]:
            if entry.get("kind") == "eval-pack" and entry.get("id") == "typed-governance-track-core":
                entry["status"] = "promoted"
                break

        with patch.object(abfr.urr, "load_registry", return_value=broken_registry):
            report = abfr.validate_alpha_backlog_fence_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn(
            "registry_protected_ref_promoted:eval-pack:typed-governance-track-core:0.32.0:promoted",
            report["failures"],
        )

    def test_auto_promotion_or_stable_alpha_gates_are_blocked(self) -> None:
        policy_path = ROOT / "configs" / "alpha-backlog-fence.json"
        policy = abfr.load_policy(policy_path)
        example_set = abfr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "alpha_backlog_fence.example.json")
        broken_set = copy.deepcopy(example_set)
        broken_set["fences"][0]["alpha_gates_stable"] = true_value = True
        broken_set["fences"][0]["promotion"]["auto_promotion_allowed"] = true_value
        broken_set["fences"][0]["promotion"]["promotion_blocked"] = False

        with patch.object(abfr, "load_example_set", return_value=broken_set):
            report = abfr.validate_alpha_backlog_fence_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("fence_alpha_gates_stable_not_false:alpha-backlog-fence-typed-governance", report["failures"])
        self.assertIn("fence_auto_promotion_allowed:alpha-backlog-fence-typed-governance", report["failures"])
        self.assertIn("fence_promotion_not_blocked:alpha-backlog-fence-typed-governance", report["failures"])

    def test_required_gate_evidence_must_be_present(self) -> None:
        policy_path = ROOT / "configs" / "alpha-backlog-fence.json"
        policy = abfr.load_policy(policy_path)
        example_set = abfr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "alpha_backlog_fence.example.json")
        broken_set = copy.deepcopy(example_set)
        broken_set["fences"][0]["required_evidence"] = broken_set["fences"][0]["required_evidence"][:1]

        with patch.object(abfr, "load_example_set", return_value=broken_set):
            report = abfr.validate_alpha_backlog_fence_policy(
                policy,
                project_root=PROJECT_ROOT,
                package_root=ROOT,
                policy_path=policy_path,
            )

        self.assertFalse(report["ok"])
        self.assertIn("fence_required_evidence_missing:alpha-backlog-fence-typed-governance", report["failures"])


if __name__ == "__main__":
    unittest.main()

