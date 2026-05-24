#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_ci_model_gates_qa.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: QA-test CI model gates discoverability through registry, backlog and changelog docs.
Inputs: Unified Registry, CI model gates policy and canonical documentation files.
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

import ci_model_gates_runtime as cmgr
import unified_registry_runtime as urr


class CIModelGatesQATests(unittest.TestCase):
    def test_ci_model_gates_pack_is_registered_and_attached_to_model_entry(self) -> None:
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
        pack = entries.get("eval-pack:ci-model-gates-core:0.32.0")
        self.assertIsNotNone(pack)
        self.assertIn("configs/ci-model-gates.json", pack["refs"])
        self.assertIn("src/ci_model_gates_runtime.py", pack["refs"])
        self.assertIn("tests/test_ci_model_gates_performance.py", pack["refs"])

        model = entries["model:model-registry-local:0.31.13.alpha-patched1"]
        self.assertIn("eval-pack:ci-model-gates-core:0.32.0", model["eval_pack_refs"])

    def test_ci_model_gates_docs_and_release_evidence_are_discoverable(self) -> None:
        policy = cmgr.load_policy(ROOT / "configs" / "ci-model-gates.json")
        self.assertEqual("CIModelGatesPolicy", policy["kind"])
        self.assertIn("prelaunch/evidence/ci-model-gates/release_evidence.json", policy["refs"])

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("CI_Model_Gates", text)


if __name__ == "__main__":
    unittest.main()

