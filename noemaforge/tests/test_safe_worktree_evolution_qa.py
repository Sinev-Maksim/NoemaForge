#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_safe_worktree_evolution_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: QA-test registry and documentation coverage for safe evolution worktrees.
Inputs: Unified Registry, safe worktree policy and canonical docs.
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

import safe_worktree_evolution_runtime as swe
import unified_registry_runtime as urr

PACK_ID = "safe-worktree-evolution-core"
CLOSED_ITEM = "[x] Add safe worktree creation for `evolution` pipeline."


class SafeWorktreeEvolutionQATests(unittest.TestCase):
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
        pack = entries.get(f"eval-pack:{PACK_ID}:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/safe-worktree-evolution-policy.json", pack["refs"])
        self.assertIn("contracts/safe_worktree_evolution.schema.json", pack["refs"])
        self.assertIn("src/safe_worktree_evolution_runtime.py", pack["refs"])
        self.assertIn("src/pipeline_runtime.py", pack["refs"])
        pipeline = entries.get("pipeline:firstboot-model-selection:0.32.1")
        self.assertIsNotNone(pipeline)
        self.assertIn(f"eval-pack:{PACK_ID}:0.32.1", pipeline["eval_pack_refs"])

    def test_docs_close_safe_worktree_todo_with_contract_refs(self) -> None:
        report = swe.validate_safe_worktree_evolution_policy(
            swe.load_policy(),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
        )
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
            self.assertIn("worktree", text.lower(), str(path))
            self.assertIn("evolution", text.lower(), str(path))

    def test_contract_runtime_is_offline_scanner(self) -> None:
        text = (ROOT / "src" / "safe_worktree_evolution_runtime.py").read_text(encoding="utf-8")
        for banned in ["import subprocess", "os.system", "Popen", "socket", "requests", "urllib"]:
            self.assertNotIn(banned, text)


if __name__ == "__main__":
    unittest.main()

