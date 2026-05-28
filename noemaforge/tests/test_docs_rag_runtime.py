#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_docs_rag_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate the deterministic local docs RAG runtime seed.
Inputs: Temporary Markdown fixtures under the tests directory.
Outputs: unittest assertions only.
Side effects: Creates and removes a temporary fixture directory.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

import docs_rag_runtime as drr
import production_ai_contracts as pac


class DocsRAGRuntimeTests(unittest.TestCase):
    def test_docs_rag_builds_answers_and_passes_rag_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="docs-rag-", dir=os.path.dirname(__file__)) as tmp:
            root = Path(tmp)
            model_doc = root / "docs" / "wiki" / "first-start" / "model.md"
            trace_doc = root / "docs" / "wiki" / "operations" / "trace.md"
            model_doc.parent.mkdir(parents=True, exist_ok=True)
            trace_doc.parent.mkdir(parents=True, exist_ok=True)
            model_doc.write_text(
                "# Model selection modes\n\n"
                "Optimize model for Dev Team means selecting a local model profile for developer workflows "
                "while preserving trace evidence and rollback context.\n",
                encoding="utf-8",
            )
            trace_doc.write_text(
                "# Trace observability\n\n"
                "Trace IDs connect model selection, Admin jobs, evaluation gates and release evidence.\n",
                encoding="utf-8",
            )

            index = drr.build_docs_index(root)
            self.assertEqual(2, index["stats"]["documents"])

            answer = drr.answer_docs_question(
                index,
                "What does optimize model for Dev Team mean?",
                top_k=2,
                max_citations=2,
            )
            self.assertTrue(answer["grounded"], answer)
            self.assertEqual("docs_rag_answer", answer["mode"])
            self.assertIn("docs/wiki/first-start/model.md", answer["retrieved_refs"])
            self.assertTrue(answer["citations"])

            case = {
                "id": "docs_model_selection_dev_team",
                "query": "What does optimize model for Dev Team mean?",
                "expected_source_refs": ["docs/wiki/first-start/model.md"],
                "expected_answer_terms": ["model", "dev team", "trace"],
            }
            result = drr.answer_result_to_rag_eval_result(answer, case_id=case["id"])
            report = pac.evaluate_rag_eval_cases([case], [result], trace_id="trace-docs-rag")
            self.assertTrue(report["ok"], report)

            gate = pac.evaluate_gate(
                {"change_id": "docs-rag-runtime-v1", "domain": "rag"},
                pac.rag_eval_report_to_gate_evidence(report, artifact_uri="reports/docs-rag.json"),
            )
            self.assertTrue(gate["ok"], gate)

    def test_docs_rag_emits_gap_notice_when_sources_do_not_match(self) -> None:
        with tempfile.TemporaryDirectory(prefix="docs-rag-gap-", dir=os.path.dirname(__file__)) as tmp:
            root = Path(tmp)
            doc = root / "docs" / "wiki" / "operations" / "launcher.md"
            doc.parent.mkdir(parents=True, exist_ok=True)
            doc.write_text("# Launcher\n\nFirst-start launcher recovery and audit notes.\n", encoding="utf-8")

            index = drr.build_docs_index(root)
            answer = drr.answer_docs_question(index, "unmapped hardware calibration topic")

            self.assertFalse(answer["grounded"])
            self.assertEqual("knowledge_gap_notice", answer["mode"])
            self.assertEqual([], answer["citations"])


if __name__ == "__main__":
    unittest.main()
