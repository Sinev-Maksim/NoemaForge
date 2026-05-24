#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_graph_patch_provenance_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Runtime-test graph patch provenance validation.
Inputs: Graph patch provenance policy, example patches and runtime validator.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import graph_patch_provenance_runtime as gpp


class GraphPatchProvenanceRuntimeTests(unittest.TestCase):
    def test_policy_validation_passes(self) -> None:
        report = gpp.validate_graph_patch_provenance_policy(gpp.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        summary = report["graph_patch_provenance_summary"]
        self.assertTrue(summary["patch_format_defined"])
        self.assertTrue(summary["schema_contract_present"])
        self.assertFalse(summary["live_graph_mutation"])
        self.assertEqual(7, summary["allowed_operation_type_count"])
        self.assertEqual(1, summary["example_patch_count"])

    def test_patch_requires_sha256_source_graph_digest(self) -> None:
        example = gpp.load_example(ROOT.parent / "prelaunch" / "governance" / "graph_patch_provenance.example.json")
        patch = copy.deepcopy(example["patches"][0])
        patch["source_graph_digest"] = "sha256:not-a-real-hash"
        failures = gpp._graph_patch_failures(patch)
        self.assertIn("patch_source_graph_digest_invalid", failures)

    def test_operation_requires_provenance_refs(self) -> None:
        example = gpp.load_example(ROOT.parent / "prelaunch" / "governance" / "graph_patch_provenance.example.json")
        patch = copy.deepcopy(example["patches"][0])
        provenance = patch["operations"][0]["provenance"]
        provenance["source_refs"] = []
        provenance["artifact_refs"] = []
        failures = gpp._graph_patch_failures(patch)
        self.assertIn("provenance_refs_empty:op:add-claim:operator-summary", failures)

    def test_unknown_operation_type_is_rejected(self) -> None:
        example = gpp.load_example(ROOT.parent / "prelaunch" / "governance" / "graph_patch_provenance.example.json")
        patch = copy.deepcopy(example["patches"][0])
        patch["operations"][0]["op_type"] = "rewrite_graph_without_review"
        failures = gpp._graph_patch_failures(patch)
        self.assertIn("operation_type_invalid:op:add-claim:operator-summary:rewrite_graph_without_review", failures)


if __name__ == "__main__":
    unittest.main()
