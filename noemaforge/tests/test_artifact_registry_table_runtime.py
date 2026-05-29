#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_artifact_registry_table_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Unit-test artifact registry table validation for outputs, reviews and graph patches.
Inputs: Artifact registry table policy and example table.
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

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import artifact_registry_table_runtime as art


class ArtifactRegistryTableRuntimeTests(unittest.TestCase):
    def test_policy_validates_with_example_records(self) -> None:
        report = art.validate_artifact_registry_table_policy(
            art.load_policy(),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
        )
        self.assertTrue(report["ok"], report["failures"])
        summary = report["artifact_registry_table_summary"]
        self.assertEqual(3, summary["record_count"])
        self.assertEqual({"outputs": 1, "reviews": 1, "graph_patches": 1}, summary["table_counts"])
        self.assertEqual({"not_required": 1, "approved": 1, "pending": 1}, summary["review_state_counts"])
        self.assertEqual(1, summary["graph_patch_records"])
        self.assertEqual(3, summary["hashed_records"])

    def test_rejects_unsafe_path_and_bad_hash(self) -> None:
        example = copy.deepcopy(art.load_example())
        example["records"][0]["path"] = "../escape.json"
        example["records"][1]["sha256"] = "bad"
        failures = art._example_failures(example, policy=art._policy_dict(art.load_policy()))["failures"]
        self.assertIn("artifact_path_invalid:0", failures)
        self.assertIn("artifact_sha256_invalid:1", failures)

    def test_review_and_graph_patch_rows_have_required_links(self) -> None:
        example = copy.deepcopy(art.load_example())
        del example["records"][1]["reviewer"]
        example["records"][2]["graph_patch_ref"] = "N/A"
        failures = art._example_failures(example, policy=art._policy_dict(art.load_policy()))["failures"]
        self.assertIn("artifact_reviewer_missing:1", failures)
        self.assertIn("artifact_graph_patch_ref_missing:2", failures)

    def test_duplicate_artifact_ids_are_rejected(self) -> None:
        example = copy.deepcopy(art.load_example())
        example["records"][2]["artifact_id"] = example["records"][0]["artifact_id"]
        failures = art._example_failures(example, policy=art._policy_dict(art.load_policy()))["failures"]
        self.assertIn("artifact_id_duplicate:2:artifact:pipeline-output:run-001", failures)


if __name__ == "__main__":
    unittest.main()
