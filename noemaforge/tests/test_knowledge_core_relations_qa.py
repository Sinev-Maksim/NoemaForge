#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_knowledge_core_relations_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Knowledge Core Relations discoverability through registry and docs.
Inputs: Unified Registry, Knowledge Core Relations policy and canonical documentation files.
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

import knowledge_core_relations_runtime as kcr
import unified_registry_runtime as urr


class KnowledgeCoreRelationsQATests(unittest.TestCase):
    CLOSURE = "Closed by `knowledge-core-relations-gates-core`"

    def test_knowledge_core_relations_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:knowledge-core-relations-gates-core:0.32.2")
        self.assertIsNotNone(pack)
        self.assertIn("configs/knowledge-core-relations-policy.json", pack["refs"])
        self.assertIn("contracts/knowledge_core_relations.schema.json", pack["refs"])
        self.assertIn("tests/test_knowledge_core_relations_performance.py", pack["refs"])
        self.assertIn("src/knowledge/gatekeeper.py", pack["refs"])
        self.assertIn("src/knowledge/store.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.2"]
        self.assertIn("eval-pack:knowledge-core-relations-gates-core:0.32.2", pipeline["eval_pack_refs"])
        self.assertIn("configs/knowledge-core-relations-policy.json", pipeline["refs"])
        self.assertIn("src/knowledge_core_relations_runtime.py", pipeline["refs"])
        self.assertIn("src/knowledge/gatekeeper.py", pipeline["refs"])

    def test_public_docs_and_todo_capture_core_relations_boundary(self) -> None:
        policy = kcr.load_policy(ROOT / "configs" / "knowledge-core-relations-policy.json")
        phrase = policy["policy"]["boundary_phrase"]
        validation = kcr.validate_knowledge_core_relations_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(validation["ok"], validation["failures"])

        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(phrase, text)
        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertIn("[x] Lock the core relations and publication gates.", backlog)

    def test_knowledge_core_relations_boundary_is_closed_in_canonical_docs(self) -> None:
        phrase = kcr.load_policy(ROOT / "configs" / "knowledge-core-relations-policy.json")["policy"]["boundary_phrase"]
        closed_line = f"- [x] {phrase} {self.CLOSURE}"
        legacy_open_line = f"- {phrase}"

        for path in [
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(closed_line, text)
            self.assertNotIn(legacy_open_line, text)

        changelog = (ROOT / "docs" / "history" / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(phrase, changelog)
        self.assertIn("knowledge-core-relations-gates-core", changelog)


if __name__ == "__main__":
    unittest.main()

