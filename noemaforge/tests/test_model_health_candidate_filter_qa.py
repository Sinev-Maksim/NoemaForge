#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_model_health_candidate_filter_qa.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test failed-model candidate filter discoverability through registry and docs.
Inputs: Unified Registry, model health candidate filter policy and canonical documentation files.
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

import model_health_candidate_filter_runtime as mhcf
import unified_registry_runtime as urr

CLOSURE = "Closed by `model-health-candidate-filter-core`"


class ModelHealthCandidateFilterQATests(unittest.TestCase):
    def test_filter_pack_is_registered_and_attached_to_firstboot_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:model-health-candidate-filter-core:0.32.0")
        self.assertIsNotNone(pack)
        self.assertIn("configs/model-health-candidate-filter-policy.json", pack["refs"])
        self.assertIn("contracts/model_health_candidate_filter.schema.json", pack["refs"])
        self.assertIn("src/model_health_candidate_filter_runtime.py", pack["refs"])
        self.assertIn("src/role_tournament.py", pack["refs"])
        self.assertIn("tests/test_model_health_candidate_filter_runtime.py", pack["refs"])
        self.assertIn("docs/TODO.md", pack["refs"])
        self.assertIn("docs/reference/PROJECT_CONTEXT.md", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.31.13.alpha-patched1"]
        self.assertIn("eval-pack:model-health-candidate-filter-core:0.32.0", pipeline["eval_pack_refs"])
        self.assertIn("configs/model-health-candidate-filter-policy.json", pipeline["refs"])
        self.assertIn("src/model_health_candidate_filter_runtime.py", pipeline["refs"])

    def test_policy_docs_and_changelog_record_closed_candidate_filter_item(self) -> None:
        policy = mhcf.load_policy(ROOT / "configs" / "model-health-candidate-filter-policy.json")
        report = mhcf.validate_model_health_candidate_filter_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        item = "Confirm no failed-runtime model remains in `role-candidate-map.filtered.json`."
        for path in [
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"[x] {item}", text, str(path))
            self.assertIn(CLOSURE, text, str(path))

        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("model-health-candidate-filter-core", text, str(path))
            self.assertIn("role-candidate-map.filtered.json", text, str(path))
            self.assertIn(CLOSURE, text, str(path))


if __name__ == "__main__":
    unittest.main()

