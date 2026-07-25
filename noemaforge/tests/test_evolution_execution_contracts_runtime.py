#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_evolution_execution_contracts_runtime.py
Zone: release/package
Version: 0.33.0
Created: 2026-07-18
Modified: 2026-07-18
Purpose: Regression-test NF-native Evolution execution contracts for issue 266.
Inputs: Contract schemas, local example set and in-memory negative fixtures.
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
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import evolution_execution_contracts_runtime as eec


CHECK_TIME = datetime(2026, 7, 18, 20, 0, 0, tzinfo=timezone.utc)


class EvolutionExecutionContractsRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.example_set = eec.load_example_set()
        self.examples = self.example_set["examples"]

    def test_all_contract_schemas_and_examples_validate(self) -> None:
        report = eec.validate_all(now=CHECK_TIME)
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(len(eec.CONTRACT_KINDS), report["example_report"]["example_count"])
        self.assertFalse(report["runtime_effects"]["starts_processes"])
        self.assertFalse(report["runtime_effects"]["mutates_github"])
        self.assertFalse(report["runtime_effects"]["invokes_model"])
        self.assertFalse(report["runtime_effects"]["mutates_services"])
        self.assertFalse(report["runtime_effects"]["mutates_live_state"])

    def test_schemas_are_draft_2020_12_and_strict_at_top_level(self) -> None:
        for schema_path in eec.schema_paths():
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
            self.assertFalse(schema["additionalProperties"], schema_path)
            failures = eec._schema_failures(schema, path=schema_path)
            self.assertEqual([], failures, schema_path)

    def test_manual_gate_pass_requires_manual_marker(self) -> None:
        gate = copy.deepcopy(self.examples["EvolutionReleaseGateResult"])
        gate["gate_type"] = "manual"
        gate["status"] = "passed"
        gate["operator_approved"] = True
        gate["manual_marker"] = ""
        failures = eec.validate_manual_gate(gate)
        self.assertIn("manual_gate_passed_without_manual_marker", failures)

    def test_manual_gate_pass_requires_operator_approval(self) -> None:
        gate = copy.deepcopy(self.examples["EvolutionReleaseGateResult"])
        gate["gate_type"] = "manual"
        gate["status"] = "passed"
        gate["operator_approved"] = False
        gate["manual_marker"] = "target-operator-approved-20260718"
        failures = eec.validate_manual_gate(gate)
        self.assertIn("manual_gate_passed_without_operator_approval", failures)

    def test_rejects_stale_and_non_independent_review_evidence(self) -> None:
        review = copy.deepcopy(self.examples["EvolutionIndependentReviewEvidence"])
        review["reviewer_agent_id"] = review["producer_agent_id"]
        review["target_head"] = "bbb5137a0f3370fe4ce61503b9cde14004621f35"
        review["fresh_until"] = "2026-07-18T19:00:00Z"
        failures = eec.validate_independent_review(review, now=CHECK_TIME)
        self.assertIn("review_evidence_not_independent", failures)
        self.assertIn("review_evidence_stale_head", failures)
        self.assertIn("review_evidence_stale_time", failures)

    def test_rejects_mutation_evidence_claiming_imported_or_shipped_reference(self) -> None:
        evidence = copy.deepcopy(self.examples["EvolutionMutationEvidence"])
        evidence["reference_source_policy"]["imported_reference_source"] = True
        evidence["reference_source_policy"]["shipped_reference_runtime"] = True
        evidence["reference_source_policy"]["source_sample_disposition"] = "bundled_with_release"
        failures = eec.validate_mutation_evidence(evidence)
        self.assertIn("mutation_evidence_claims_imported_reference_source", failures)
        self.assertIn("mutation_evidence_claims_shipped_reference_runtime", failures)
        self.assertIn("mutation_evidence_reference_source_not_local_only", failures)

    def test_unknown_top_level_fields_are_rejected(self) -> None:
        run = copy.deepcopy(self.examples["EvolutionRun"])
        run["surprise_runtime_launcher"] = "noemaforge first-start"
        failures = eec.validate_contract_doc(run, now=CHECK_TIME)
        self.assertIn("EvolutionRun:unknown_top_level_fields:surprise_runtime_launcher", failures)

    def test_heavy_resource_lease_preserves_single_worker_and_approval_invariants(self) -> None:
        lease = copy.deepcopy(self.examples["EvolutionResourceLease"])
        lease["exclusive"] = False
        lease["approval_required"] = False
        lease["one_active_heavy_worker_limit"] = False
        failures = eec.validate_contract_doc(lease, now=CHECK_TIME)
        self.assertIn("resource_lease_heavy_not_exclusive", failures)
        self.assertIn("resource_lease_heavy_without_approval", failures)
        self.assertIn("resource_lease_heavy_limit_missing", failures)


if __name__ == "__main__":
    unittest.main()
