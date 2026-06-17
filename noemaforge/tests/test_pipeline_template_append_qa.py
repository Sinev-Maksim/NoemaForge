#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_template_append_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test reviewed pipeline template append discoverability through registry and docs.
Inputs: Unified Registry, template-append policy and canonical documentation files.
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

import pipeline_template_append_runtime as ptar
import unified_registry_runtime as urr


class PipelineTemplateAppendQATests(unittest.TestCase):
    def test_pipeline_template_append_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:pipeline-template-append-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/pipeline-template-append-policy.json", pack["refs"])
        self.assertIn("contracts/pipeline_template_append.schema.json", pack["refs"])
        self.assertIn("src/pipeline_runtime.py", pack["refs"])
        self.assertIn("src/pipeline_template_append_runtime.py", pack["refs"])
        self.assertIn("tests/test_pipeline_template_append_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:pipeline-template-append-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/pipeline-template-append-policy.json", pipeline["refs"])
        self.assertIn("src/pipeline_template_append_runtime.py", pipeline["refs"])

    def test_pipeline_template_append_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = ptar.load_policy(ROOT / "configs" / "pipeline-template-append-policy.json")
        self.assertEqual("PipelineTemplateAppendPolicy", policy["kind"])
        self.assertEqual("reviewed_template_catalog_append", policy["policy"]["activation_state"])
        self.assertIn("template-append", policy["policy"]["required_pipeline_commands"])

        validation = ptar.validate_pipeline_template_append_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(validation["ok"], validation["failures"])

        _existing_docs = [p for p in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Turn `template-import` drafts into an explicit reviewed catalog-append workflow.", text)
            self.assertIn("pipeline-template-append-core", text)

        _existing_docs = [p for p in [
            PROJECT_ROOT / "docs" / "README.md",
            ROOT / "docs" / "README.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn("pipeline-template-append-core", text)
            self.assertIn("noemaforge pipeline template-append", text)


if __name__ == "__main__":
    unittest.main()

