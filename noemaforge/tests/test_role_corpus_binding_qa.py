#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_role_corpus_binding_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Role Corpus Binding discoverability through registry and docs.
Inputs: Unified Registry, Role Corpus Binding policy and canonical documentation files.
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

import role_corpus_binding_runtime as rcb
import unified_registry_runtime as urr
from firstboot_eval import default_eval_surface


class RoleCorpusBindingQATests(unittest.TestCase):
    CLOSURE = "Closed by `role-corpus-binding-core`"

    def test_role_corpus_binding_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:role-corpus-binding-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/role-corpus-binding-policy.json", pack["refs"])
        self.assertIn("configs/role-eval-datasets.yaml", pack["refs"])
        self.assertIn("tests/test_role_corpus_binding_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:role-corpus-binding-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/role-corpus-binding-policy.json", pipeline["refs"])
        self.assertIn("src/role_corpus_binding_runtime.py", pipeline["refs"])

    def test_public_docs_and_todo_capture_role_corpus_boundary(self) -> None:
        policy = rcb.load_policy(ROOT / "configs" / "role-corpus-binding-policy.json")
        phrase = policy["policy"]["boundary_phrase"]
        validation = rcb.validate_role_corpus_binding_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
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
        self.assertIn("[x] Keep role-scoped JSONL suites for system evaluation.", backlog)
        self.assertIn("[x] If the required dataset/corpus is missing, mark the role as `N/A` instead of silently faking coverage.", backlog)

    def test_role_corpus_binding_boundary_is_closed_in_canonical_docs(self) -> None:
        phrase = rcb.load_policy(ROOT / "configs" / "role-corpus-binding-policy.json")["policy"]["boundary_phrase"]
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
        self.assertIn("role-corpus-binding-core", changelog)

    def test_firstboot_eval_surface_loads_role_catalog_without_external_yaml_dependency(self) -> None:
        catalog = rcb.load_role_eval_catalog(ROOT / "configs" / "role-eval-datasets.yaml")
        expected = sorted(tuple(str(key).split("/", 1)) for key in (catalog.get("roles") or {}) if "/" in str(key))
        self.assertEqual(expected, sorted(default_eval_surface()))


if __name__ == "__main__":
    unittest.main()

