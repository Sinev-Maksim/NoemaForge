#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_knowledge_purpose_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Knowledge Purpose discoverability through registry and docs.
Inputs: Unified Registry, Knowledge Purpose policy and canonical documentation files.
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

import knowledge_purpose_runtime as kpr
import unified_registry_runtime as urr


class KnowledgePurposeQATests(unittest.TestCase):
    CLOSURE = "Closed by `knowledge-purpose-artifacts-core`"

    def test_knowledge_purpose_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:knowledge-purpose-artifacts-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/knowledge-purpose-policy.json", pack["refs"])
        self.assertIn("contracts/knowledge_purpose.schema.json", pack["refs"])
        self.assertIn("tests/test_knowledge_purpose_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:knowledge-purpose-artifacts-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/knowledge-purpose-policy.json", pipeline["refs"])
        self.assertIn("src/knowledge_purpose_runtime.py", pipeline["refs"])

    def test_public_docs_and_todo_capture_knowledge_purpose_boundary(self) -> None:
        policy = kpr.load_policy(ROOT / "configs" / "knowledge-purpose-policy.json")
        phrase = policy["policy"]["boundary_phrase"]
        validation = kpr.validate_knowledge_purpose_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
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
        self.assertIn("[x] Define a `purpose.md` or equivalent typed artifact per knowledge realm/project.", backlog)
        self.assertIn("[x] Use this artifact during ingest, lint, and review.", backlog)

    def test_knowledge_purpose_boundary_is_closed_in_canonical_docs(self) -> None:
        phrase = kpr.load_policy(ROOT / "configs" / "knowledge-purpose-policy.json")["policy"]["boundary_phrase"]
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
        self.assertIn("knowledge-purpose-artifacts-core", changelog)


if __name__ == "__main__":
    unittest.main()

