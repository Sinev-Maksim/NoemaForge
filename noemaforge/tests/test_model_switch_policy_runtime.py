#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_model_switch_policy_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Unit-test role-driven model switch policy decisions.
Inputs: Model switch policy and example inventory.
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

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import model_switch_policy_runtime as msp


class ModelSwitchPolicyRuntimeTests(unittest.TestCase):
    def test_policy_validates_with_example_matrix(self) -> None:
        report = msp.validate_model_switch_policy(msp.load_policy(), project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        summary = report["model_switch_policy_summary"]
        self.assertGreaterEqual(summary["role_count"], 6)
        self.assertTrue(summary["local_first"])
        self.assertTrue(summary["remote_requires_explicit_approval"])
        self.assertTrue(summary["silent_fallback_blocked"])

    def test_local_preferred_wins_without_remote_approval(self) -> None:
        policy = msp.load_policy()
        example = msp.load_example()
        decision = msp.resolve_model_switch(policy, "administrator", example["model_inventory"], remote_approved=False)
        self.assertEqual("selected", decision["decision"])
        self.assertEqual("local:qwen2.5-7b-instruct", decision["selected_model_id"])
        self.assertEqual("preferred_local_models", decision["selected_source"])

    def test_remote_preferred_requires_explicit_approval(self) -> None:
        policy = msp.load_policy()
        inventory = [
            {
                "model_id": "remote:frontier-research",
                "backend": "remote",
                "status": "available",
                "health": "pass",
                "approved": True,
            },
            {
                "model_id": "local:main",
                "backend": "local",
                "status": "available",
                "health": "pass",
                "approved": True,
            },
        ]
        blocked = msp.resolve_model_switch(policy, "researcher", inventory, remote_approved=False)
        approved = msp.resolve_model_switch(policy, "researcher", inventory, remote_approved=True)
        self.assertEqual("local:main", blocked["selected_model_id"])
        self.assertIn("remote_requires_approval", {item["status"] for item in blocked["checked_candidates"]})
        self.assertEqual("remote:frontier-research", approved["selected_model_id"])

    def test_unmapped_role_returns_na_instead_of_silent_fallback(self) -> None:
        decision = msp.resolve_model_switch(msp.load_policy(), "not_a_role", msp.load_example()["model_inventory"])
        self.assertEqual("role_unmapped", decision["decision"])
        self.assertEqual("N/A", decision["selected_model_id"])


if __name__ == "__main__":
    unittest.main()
