#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_hypergraph_error_improvement_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Hypergraph Error Improvement discoverability through registry and docs.
Inputs: Unified Registry, Hypergraph Error Improvement policy and canonical documentation files.
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

import hypergraph_error_improvement_runtime as hei
import unified_registry_runtime as urr


class HypergraphErrorImprovementQATests(unittest.TestCase):
    CLOSURE = "Closed by `hypergraph-error-improvement-core`"

    def test_pack_is_registered_and_attached_to_firstboot_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:hypergraph-error-improvement-core:0.32.2")
        self.assertIsNotNone(pack)
        self.assertIn("configs/hypergraph-error-improvement-policy.json", pack["refs"])
        self.assertIn("sql/error_learning_loop.sqlite.sql", pack["refs"])
        self.assertIn("tests/test_hypergraph_error_improvement_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.2"]
        self.assertIn("eval-pack:hypergraph-error-improvement-core:0.32.2", pipeline["eval_pack_refs"])
        self.assertIn("configs/hypergraph-error-improvement-policy.json", pipeline["refs"])
        self.assertIn("src/hypergraph_error_improvement_runtime.py", pipeline["refs"])

    def test_public_docs_and_todo_capture_hypergraph_error_boundary(self) -> None:
        policy = hei.load_policy(ROOT / "configs" / "hypergraph-error-improvement-policy.json")
        phrase = policy["policy"]["boundary_phrase"]
        validation = hei.validate_hypergraph_error_improvement_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
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
        self.assertIn("[x] Create `error_events`, `corrections`, and `regression_cases` stores.", backlog)
        self.assertIn("[x] Track which model/run/profile produced each error.", backlog)

    def test_hypergraph_error_improvement_boundary_is_closed_in_canonical_docs(self) -> None:
        phrase = hei.load_policy(ROOT / "configs" / "hypergraph-error-improvement-policy.json")["policy"]["boundary_phrase"]
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
        self.assertIn("hypergraph-error-improvement-core", changelog)


if __name__ == "__main__":
    unittest.main()

