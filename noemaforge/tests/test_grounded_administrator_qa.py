#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_grounded_administrator_qa.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Grounded Administrator discoverability through registry and docs.
Inputs: Unified Registry, Grounded Administrator policy and canonical documentation files.
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

import grounded_administrator_runtime as gar
import unified_registry_runtime as urr


class GroundedAdministratorQATests(unittest.TestCase):
    def test_grounded_administrator_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:grounded-administrator-core:0.32.0")
        self.assertIsNotNone(pack)
        self.assertIn("configs/grounded-administrator-policy.json", pack["refs"])
        self.assertIn("contracts/grounded_administrator.schema.json", pack["refs"])
        self.assertIn("manifests/functional/knowledge.hypergraph.yaml", pack["refs"])
        self.assertIn("src/knowledge/grounded_administrator.py", pack["refs"])
        self.assertIn("tests/test_grounded_administrator_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.31.13.alpha-patched1"]
        self.assertIn("eval-pack:grounded-administrator-core:0.32.0", pipeline["eval_pack_refs"])
        self.assertIn("configs/grounded-administrator-policy.json", pipeline["refs"])
        self.assertIn("src/grounded_administrator_runtime.py", pipeline["refs"])

    def test_public_docs_and_todo_capture_grounded_administrator_boundary(self) -> None:
        policy = gar.load_policy(ROOT / "configs" / "grounded-administrator-policy.json")
        phrase = policy["policy"]["boundary_phrase"]
        validation = gar.validate_grounded_administrator_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(validation["ok"], validation["failures"])

        for path in [
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "docs" / "README.md",
            ROOT / "docs" / "README.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(phrase, text)
        self.assertIn("[x] Grounded Administrator as the default knowledge surface.", (PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

