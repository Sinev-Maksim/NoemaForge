#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_graph_projection_views_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Graph Projection Views discoverability through registry and docs.
Inputs: Unified Registry, Graph Projection Views policy and canonical documentation files.
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

import graph_projection_views_runtime as gpv
import unified_registry_runtime as urr

CLOSURE = "Closed by `graph-projection-views-core`"


class GraphProjectionViewsQATests(unittest.TestCase):
    def test_graph_projection_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:graph-projection-views-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/graph-projection-views-policy.json", pack["refs"])
        self.assertIn("contracts/graph_projection_views.schema.json", pack["refs"])
        self.assertIn("tests/test_graph_projection_views_performance.py", pack["refs"])
        self.assertIn("docs/TODO.md", pack["refs"])
        self.assertIn("docs/reference/PROJECT_CONTEXT.md", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:graph-projection-views-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/graph-projection-views-policy.json", pipeline["refs"])
        self.assertIn("src/graph_projection_views_runtime.py", pipeline["refs"])

    def test_public_docs_and_todo_capture_graph_projection_boundary(self) -> None:
        policy = gpv.load_policy(ROOT / "configs" / "graph-projection-views-policy.json")
        phrase = policy["policy"]["boundary_phrase"]
        validation = gpv.validate_graph_projection_views_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(validation["ok"], validation["failures"])

        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(phrase, text)
            self.assertIn(CLOSURE, text)
        closed_item = "[x] Keep wiki-like pages as projections/views derived from the graph."
        self.assertIn(closed_item, (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8"))
        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        for item in [
            "[x] Add a wiki/markdown projection from the graph.",
            "[x] Add an operator projection summarizing what the system currently \"knows\" and what is uncertain.",
            "[x] Add a task-context projection for work sessions.",
            "[x] Add conflict/review projection for unresolved issues.",
        ]:
            self.assertIn(item, backlog)

    def test_graph_projection_boundary_refs_use_canonical_docs_paths(self) -> None:
        policy = gpv.load_policy(ROOT / "configs" / "graph-projection-views-policy.json")
        refs = set(policy["policy"]["required_boundary_refs"])

        self.assertIn("docs/TODO.md", refs)
        self.assertIn("docs/reference/PROJECT_CONTEXT.md", refs)
        self.assertIn("noemaforge/docs/TODO.md", refs)
        self.assertTrue(all(ref.startswith(("docs/", "noemaforge/docs/")) for ref in refs))
        self.assertFalse({"README.md", "TODO.md", "noemaforge/TODO.md"} & refs)


if __name__ == "__main__":
    unittest.main()

