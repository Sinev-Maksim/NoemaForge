#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_memory_budgeted_retrieval_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Memory-Budgeted Retrieval discoverability through registry and docs.
Inputs: Unified Registry, Memory-Budgeted Retrieval policy and canonical documentation files.
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

import memory_budgeted_retrieval_runtime as mbr
import unified_registry_runtime as urr


class MemoryBudgetedRetrievalQATests(unittest.TestCase):
    def test_memory_budgeted_pack_is_registered_and_attached_to_pipeline(self) -> None:
        registry_path = ROOT / "configs" / "unified-registry.json"
        report = urr.validate_unified_registry(
            urr.load_registry(registry_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=registry_path,
        )
        self.assertTrue(report["ok"], report["failures"])

        entries = {
            f"{entry['kind']}:{entry['id']}:{entry['version']}": entry
            for entry in report["normalized_registry"]["entries"]
        }
        pack = entries.get("eval-pack:memory-budgeted-retrieval-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/memory-budgeted-retrieval-policy.json", pack["refs"])
        self.assertIn("contracts/memory_budgeted_retrieval.schema.json", pack["refs"])
        self.assertIn("src/knowledge/prep_pipeline.py", pack["refs"])
        self.assertIn("src/knowledge/prep_store.py", pack["refs"])
        self.assertIn("tests/test_memory_budgeted_retrieval_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:memory-budgeted-retrieval-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/memory-budgeted-retrieval-policy.json", pipeline["refs"])
        self.assertIn("src/memory_budgeted_retrieval_runtime.py", pipeline["refs"])

    def test_public_docs_and_todo_capture_memory_budgeted_boundary(self) -> None:
        policy = mbr.load_policy(ROOT / "configs" / "memory-budgeted-retrieval-policy.json")
        phrase = policy["policy"]["boundary_phrase"]
        validation = mbr.validate_memory_budgeted_retrieval_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(validation["ok"], validation["failures"])

        for path in [p for p in [
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "docs" / "README.md",
            ROOT / "docs" / "README.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ] if p.exists()]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(phrase, text)
        closed_item = "[x] If a chunk chain is too large for the active memory budget, retrieval must degrade gracefully: first pull the highest-coherence subchunks, then add supporting neighbors only if budget remains."
        self.assertIn(closed_item, (PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

