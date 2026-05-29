#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_model_profile_selection_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test model profile selection discoverability through registry, docs and CLI.
Inputs: Unified Registry, model profile selection policy and canonical docs.
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

import model_profile_selection_runtime as mps
import unified_registry_runtime as urr


class ModelProfileSelectionQATests(unittest.TestCase):
    CLOSURE = "Closed by `model-profile-selection-core`"

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
        pack = entries.get("eval-pack:model-profile-selection-core:0.32.2")
        self.assertIsNotNone(pack)
        self.assertIn("configs/model-profile-selection-policy.json", pack["refs"])
        self.assertIn("configs/model-profiles.json", pack["refs"])
        self.assertIn("docs/TODO.md", pack["refs"])
        self.assertIn("tests/test_model_profile_selection_performance.py", pack["refs"])
        pipeline = entries["pipeline:firstboot-model-selection:0.32.2"]
        self.assertIn("eval-pack:model-profile-selection-core:0.32.2", pipeline["eval_pack_refs"])
        self.assertIn("src/model_profile_selection_runtime.py", pipeline["refs"])

    def test_docs_and_backlog_capture_profile_boundary(self) -> None:
        policy = mps.load_policy(ROOT / "configs" / "model-profile-selection-policy.json")
        phrase = policy["policy"]["boundary_phrase"]
        validation = mps.validate_model_profile_selection_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(validation["ok"], validation["failures"])
        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
        ]:
            self.assertIn(phrase, path.read_text(encoding="utf-8"))
        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertIn("[x] Define `minimal`, `balanced`, `writer`, `research`, `gpu-heavy` model profiles.", backlog)
        self.assertIn("[x] Expose profile choice in `setup.sh` and firstboot.", backlog)

    def test_model_profile_boundary_is_closed_in_canonical_docs(self) -> None:
        phrase = mps.load_policy(ROOT / "configs" / "model-profile-selection-policy.json")["policy"]["boundary_phrase"]
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
        self.assertIn("model-profile-selection-core", changelog)


if __name__ == "__main__":
    unittest.main()

