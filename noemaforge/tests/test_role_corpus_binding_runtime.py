#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_role_corpus_binding_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate role corpus binding runtime behavior.
Inputs: Workspace Role Corpus Binding policy, role-eval catalog and offline example.
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

import role_corpus_binding_runtime as rcb


class RoleCorpusBindingRuntimeTests(unittest.TestCase):
    def test_workspace_role_corpus_binding_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "role-corpus-binding-policy.json"
        validation = rcb.validate_role_corpus_binding_policy(
            rcb.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertGreaterEqual(validation["metrics"]["roles"], 40)
        self.assertGreaterEqual(validation["metrics"]["available_roles"], 1)
        self.assertGreaterEqual(validation["metrics"]["na_roles"], 1)
        self.assertGreaterEqual(validation["metrics"]["jsonl_files"], 10)

    def test_missing_writer_library_roles_are_na_not_fake_coverage(self) -> None:
        catalog = rcb.load_role_eval_catalog(ROOT / "configs" / "role-eval-datasets.yaml")
        resolution = rcb.resolve_role_corpus_bindings(catalog, project_root=PROJECT_ROOT, package_root=ROOT)
        bindings = {item["role_key"]: item for item in resolution["bindings"]}

        self.assertEqual("available", bindings["operator.admin/administrator"]["binding_status"])
        self.assertEqual("N/A", bindings["writing.story/writer"]["binding_status"])
        self.assertEqual("dataset_missing", bindings["writing.story/writer"]["reason"])
        self.assertFalse(bindings["writing.story/writer"]["coverage_claimed"])

    def test_example_catalog_resolves_seed_and_missing_library(self) -> None:
        examples = rcb.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "role_corpus_binding.example.json")
        scenario = examples["scenarios"][0]
        resolution = rcb.resolve_role_corpus_bindings(scenario["catalog"], project_root=PROJECT_ROOT, package_root=ROOT)
        bindings = {item["role_key"]: item for item in resolution["bindings"]}

        self.assertEqual("available", bindings["operator.admin/administrator"]["binding_status"])
        self.assertEqual("N/A", bindings["writing.story/writer"]["binding_status"])


if __name__ == "__main__":
    unittest.main()
