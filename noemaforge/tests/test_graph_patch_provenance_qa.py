#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_graph_patch_provenance_qa.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-21
Modified: 2026-05-21
Purpose: QA-test registry and docs coverage for graph patch provenance.
Inputs: Unified Registry, graph patch provenance policy and canonical docs.
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

import graph_patch_provenance_runtime as gpp
import unified_registry_runtime as urr

PACK_ID = "graph-patch-provenance-core"
CLOSED_ITEM = "[x] Add graph patch format and provenance schema. Closed by `graph-patch-provenance-core`"


class GraphPatchProvenanceQATests(unittest.TestCase):
    def test_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get(f"eval-pack:{PACK_ID}:0.32.0")
        self.assertIsNotNone(pack)
        self.assertIn("configs/graph-patch-provenance-policy.json", pack["refs"])
        self.assertIn("contracts/graph_patch_provenance.schema.json", pack["refs"])
        self.assertIn("src/graph_patch_provenance_runtime.py", pack["refs"])
        pipeline = entries.get("pipeline:firstboot-model-selection:0.31.13.alpha-patched1")
        self.assertIsNotNone(pipeline)
        self.assertIn(f"eval-pack:{PACK_ID}:0.32.0", pipeline["eval_pack_refs"])

    def test_docs_close_pipeline_todo_with_contract_refs(self) -> None:
        report = gpp.validate_graph_patch_provenance_policy(gpp.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertIn(CLOSED_ITEM, backlog)
        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "wiki" / "pipelines" / "wiki-incremental-patch-pipeline.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(PACK_ID, text, str(path))
            self.assertIn("provenance", text.lower(), str(path))

    def test_runtime_never_applies_graph_patches(self) -> None:
        text = (ROOT / "src" / "graph_patch_provenance_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn("import subprocess", text)
        self.assertNotIn("os.system", text)
        self.assertNotIn("Popen", text)
        self.assertNotIn("sqlite3.connect", text)


if __name__ == "__main__":
    unittest.main()

