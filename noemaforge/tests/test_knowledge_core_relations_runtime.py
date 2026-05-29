#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_knowledge_core_relations_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate knowledge core relations and publication gate runtime behavior.
Inputs: Workspace Knowledge Core Relations policy and synthetic KnowledgeStore rows.
Outputs: unittest assertions only.
Side effects: Temporary SQLite stores inside test-owned temp directories.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import knowledge_core_relations_runtime as kcr
from knowledge.gatekeeper import run_gatekeeper
from knowledge.store import KnowledgeStore


class KnowledgeCoreRelationsRuntimeTests(unittest.TestCase):
    def test_workspace_knowledge_core_relations_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "knowledge-core-relations-policy.json"
        validation = kcr.validate_knowledge_core_relations_policy(
            kcr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=ROOT / "configs" / "unified-registry.json",
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(10, validation["metrics"]["frozen_object_types"])
        self.assertEqual(8, validation["metrics"]["relations"])
        self.assertEqual(4, validation["metrics"]["gate_object_kinds"])
        self.assertGreaterEqual(validation["metrics"]["boundary_refs"], 9)

    def test_gatekeeper_text_contains_current_conflict_columns_and_required_codes(self) -> None:
        text = (ROOT / "src" / "knowledge" / "gatekeeper.py").read_text(encoding="utf-8")
        report = kcr.analyze_gatekeeper_text(text, gate_codes=kcr.REQUIRED_GATE_CODES)

        self.assertTrue(report["ok"], report["failures"])
        self.assertTrue(report["checks"]["conflict_columns_current"])
        self.assertTrue(report["checks"]["gate_code:claim_confidence_below_auto_publish"])
        self.assertTrue(report["checks"]["gate_code:conflict_missing_realm"])

    def test_gatekeeper_enforces_publication_gate_decisions_on_store_rows(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nfg-knowledge-relations-") as tmp:
            store = KnowledgeStore(Path(tmp) / "kg.sqlite")
            source_id = store.add_source(source_id="source:ok", type="book", primary_realm="science")
            passage_id = store.add_passage(
                passage_id="passage:ok",
                source_id=source_id,
                anchor={"kind": "page", "page": 7},
                text="Grounded passage text.",
            )
            store.add_concept(concept_id="concept:ok", labels=["bounded retrieval"], definition_passage_ids=[passage_id])
            store.add_claim(
                claim_id="claim:ok",
                text_normalized="bounded retrieval uses graph-backed provenance",
                about_concepts=["concept:ok"],
                realm_context={"domain": "science"},
                confidence=0.93,
                extracted_from_passages=[passage_id],
            )
            store.add_claim(
                claim_id="claim:review",
                text_normalized="low confidence claim needs review",
                realm_context={"domain": "science"},
                confidence=0.45,
                extracted_from_passages=[passage_id],
            )
            store.add_conflict(
                conflict_id="conflict:ok",
                entity_a="claim:ok",
                entity_b="claim:other",
                realm_context={"domain": "science"},
                status="Unresolved",
            )
            store.add_conflict(
                conflict_id="conflict:bad",
                entity_a="claim:ok",
                entity_b="",
                realm_context={},
                status="Unknown",
            )

            summary = run_gatekeeper(store, limit_each=20)

            self.assertTrue(summary["ok"], summary)
            self.assertEqual("auto_publish", store.get_gate_report(object_kind="claim", object_id="claim:ok")["decision"])
            review_report = store.get_gate_report(object_kind="claim", object_id="claim:review")
            self.assertEqual("review", review_report["decision"])
            self.assertIn("claim_confidence_below_auto_publish", review_report["violations_json"])
            self.assertEqual("auto_publish", store.get_gate_report(object_kind="conflict", object_id="conflict:ok")["decision"])
            bad_conflict = store.get_gate_report(object_kind="conflict", object_id="conflict:bad")
            self.assertEqual("quarantine", bad_conflict["decision"])
            bad_codes = {item["code"] for item in json.loads(bad_conflict["violations_json"])}
            self.assertIn("conflict_missing_entities", bad_codes)
            self.assertIn("conflict_missing_realm", bad_codes)


if __name__ == "__main__":
    unittest.main()
