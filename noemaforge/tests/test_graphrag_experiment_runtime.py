#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_graphrag_experiment_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate the local GraphRAG experiment pack and gate evidence conversion.
Inputs: Workspace GraphRAG pack and temporary broken fixtures.
Outputs: unittest assertions only.
Side effects: Creates and removes temporary fixture directories.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import graphrag_experiment_runtime as ger
import production_ai_contracts as pac


class GraphRAGExperimentRuntimeTests(unittest.TestCase):
    def test_workspace_graphrag_experiment_pack_passes_gate(self) -> None:
        pack_path = ROOT / "configs" / "graphrag-experiment-pack.json"
        report = ger.evaluate_graphrag_experiment_pack(
            ger.load_pack(pack_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            pack_path=pack_path,
            trace_id="trace-graphrag",
        )

        self.assertTrue(report["ok"], report)
        self.assertTrue(report["validation"]["ok"], report["validation"])
        self.assertEqual("disabled", report["status"])
        self.assertEqual(1.0, report["metrics"]["retrieval_hit_rate"])
        self.assertEqual(1.0, report["metrics"]["citation_coverage"])
        self.assertEqual(1.0, report["metrics"]["graph_path_coverage"])
        self.assertEqual(1.0, report["metrics"]["multi_hop_coverage"])

        gate = pac.evaluate_gate(
            {"change_id": "graphrag-experiment-pack", "domain": "rag"},
            ger.graph_eval_report_to_gate_evidence(report, artifact_uri="reports/graphrag-experiment.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_validation_blocks_missing_refs_and_broken_graph_edges(self) -> None:
        pack_path = ROOT / "configs" / "graphrag-experiment-pack.json"
        pack = copy.deepcopy(ger.load_pack(pack_path))
        pack["refs"] = ["configs/missing-graphrag.json"]
        pack["graph"]["edges"].append({"source": "concept:graphrag", "target": "missing-node", "relation": "requires"})
        pack["policy"]["network"] = "allow"

        report = ger.validate_graphrag_experiment_pack(
            pack,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            pack_path=pack_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("policy_network_not_deny", report["failures"])
        self.assertIn("edge_target_missing:concept:graphrag->missing-node", report["failures"])
        self.assertIn("missing_ref:configs/missing-graphrag.json", report["failures"])

    def test_thresholds_block_when_expected_graph_path_is_absent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="graphrag-", dir=os.path.dirname(__file__)) as tmp:
            project = Path(tmp)
            package = project / "noemaforge"
            (package / "configs").mkdir(parents=True)
            (package / "contracts").mkdir(parents=True)
            (package / "src").mkdir(parents=True)
            (package / "configs" / "pack.json").write_text("{}", encoding="utf-8")
            (package / "contracts" / "schema.json").write_text("{}", encoding="utf-8")
            (package / "src" / "runtime.py").write_text("# runtime\n", encoding="utf-8")
            (project / "docs" / "wiki").mkdir(parents=True)
            (project / "docs" / "wiki" / "rag.md").write_text("# RAG\n\nClassic rag citations groundedness.\n", encoding="utf-8")

            pack = {
                "apiVersion": "noemaforge.graphrag-experiment/v1",
                "kind": "GraphRAGExperimentPack",
                "id": "broken-graph",
                "version": "v1",
                "status": "disabled",
                "policy": {
                    "mode": "experiment",
                    "baseline_eval_pack_ref": "eval-pack:docs-wiki-rag-core:v1",
                    "require_classic_rag_baseline": True,
                    "require_evaluation_gate": True,
                    "require_trace_id": True,
                    "require_release_evidence_before_promotion": True,
                    "network": "deny",
                    "max_graph_depth": 1,
                    "max_expansion_nodes": 3,
                    "allowed_node_types": ["concept", "source", "control"],
                    "allowed_edge_relations": ["describes", "requires", "gates", "cites", "supports"],
                },
                "thresholds": {
                    "retrieval_hit_rate_min": 1.0,
                    "citation_coverage_min": 1.0,
                    "groundedness_min": 1.0,
                    "answer_helpfulness_min": 1.0,
                    "graph_path_coverage_min": 1.0,
                    "multi_hop_coverage_min": 1.0,
                    "baseline_floor_min": 1.0,
                },
                "graph": {
                    "nodes": [
                        {"id": "concept:graphrag", "type": "concept", "title": "GraphRAG", "terms": ["graphrag"]},
                        {
                            "id": "source:rag",
                            "type": "source",
                            "title": "RAG",
                            "source_ref": "docs/wiki/rag.md",
                            "terms": ["classic rag", "citations", "groundedness"],
                        },
                    ],
                    "edges": [{"source": "concept:graphrag", "target": "source:rag", "relation": "describes"}],
                },
                "cases": [
                    {
                        "id": "missing_multihop",
                        "query": "What baseline is required?",
                        "seed_node_ids": ["concept:graphrag"],
                        "expected_source_refs": ["docs/wiki/rag.md"],
                        "expected_answer_terms": ["classic rag", "citations", "groundedness"],
                        "expected_graph_paths": [["concept:graphrag", "source:rag"]],
                    }
                ],
                "refs": ["configs/pack.json", "contracts/schema.json", "src/runtime.py", "docs/wiki/rag.md"],
            }

            report = ger.evaluate_graphrag_experiment_pack(pack, project_root=project, package_root=package)
            self.assertFalse(report["ok"], report)
            self.assertIn("multi_hop_coverage", report["threshold_failures"])
            self.assertEqual(0.0, report["metrics"]["multi_hop_coverage"])


if __name__ == "__main__":
    unittest.main()
