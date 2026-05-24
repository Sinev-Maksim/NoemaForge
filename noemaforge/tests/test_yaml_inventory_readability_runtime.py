#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_yaml_inventory_readability_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Validate YAML inventory readability policy and scanner behavior.
Inputs: YAML inventory readability policy and synthetic YAML snippets.
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

import production_ai_contracts as pac
import yaml_inventory_readability_runtime as yirr


class YamlInventoryReadabilityRuntimeTests(unittest.TestCase):
    def test_policy_validates_active_yaml_without_external_parser(self) -> None:
        policy = yirr.load_policy(ROOT / "configs" / "yaml-inventory-readability-policy.json")
        report = yirr.validate_yaml_inventory_readability_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertTrue(report["ok"], report["failures"])
        self.assertGreater(report["metrics"]["yaml_files"], 10)
        self.assertEqual("readability_and_yaml_lite_syntax_only", report["parse_scope"])

        gate = pac.evaluate_gate(
            {
                "change_id": "yaml-inventory-readability-core",
                "domain": "pipeline",
                "required_checks": ["yaml_inventory_readability", "rollback_plan"],
            },
            {
                "artifact_uri": "reports/yaml-inventory-readability.json",
                "run_at": "2026-05-21T00:00:00Z",
                "checks": [
                    {"id": "yaml_inventory_readability", "status": "passed" if report["ok"] else "failed"},
                    {"id": "rollback_plan", "status": "passed"},
                ],
            },
        )
        self.assertTrue(gate["ok"], gate)

    def test_tab_indentation_and_unclosed_flow_are_rejected(self) -> None:
        text = "root:\n\tbad: true\nitems: [one, two\n"
        failures = yirr.lint_yaml_text(text, source="synthetic.yaml")
        reasons = {item["reason"] for item in failures}

        self.assertIn("tab_indentation", reasons)
        self.assertIn("unclosed_flow_opener", reasons)

    def test_block_scalars_do_not_trigger_flow_bracket_false_positive(self) -> None:
        text = """summary: |
  Operator note with [unmatched prose bracket.
items:
  - name: safe
"""
        failures = yirr.lint_yaml_text(text, source="block-scalar.yaml")

        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()
