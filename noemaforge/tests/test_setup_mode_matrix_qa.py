#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_setup_mode_matrix_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test setup mode matrix discoverability through registry, docs and TODO.
Inputs: Unified Registry, setup mode policy and canonical documentation files.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import setup_mode_matrix_runtime as smm


class SetupModeMatrixQATests(unittest.TestCase):
    CLOSURE = "Closed by `setup-mode-matrix-core`"

    def test_pack_is_registered_and_attached_to_firstboot_pipeline(self) -> None:
        registry = json.loads((ROOT / "configs" / "unified-registry.json").read_text(encoding="utf-8"))
        entries = {f"{item['kind']}:{item['id']}:{item['version']}": item for item in registry["entries"]}
        pack_ref = "eval-pack:setup-mode-matrix-core:0.32.1"
        pack = entries.get(pack_ref)
        self.assertIsNotNone(pack)
        self.assertIn("configs/setup-modes.json", pack["refs"])
        self.assertIn("tests/test_setup_mode_matrix_performance.py", pack["refs"])
        self.assertIn("prelaunch/governance/setup_mode_matrix.example.json", pack["refs"])
        self.assertIn("docs/TODO.md", pack["refs"])
        self.assertIn("docs/onboarding/SETUP_MODES.md", pack["refs"])
        self.assertIn("docs/reference/PROJECT_CONTEXT.md", pack["refs"])
        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn(pack_ref, pipeline["eval_pack_refs"])
        self.assertIn("configs/setup-mode-matrix-policy.json", pipeline["refs"])
        self.assertIn("configs/setup-modes.json", pipeline["refs"])
        self.assertIn("src/setup_mode_matrix_runtime.py", pipeline["refs"])

    def test_public_docs_and_todo_capture_setup_mode_boundary(self) -> None:
        policy = smm.load_policy(ROOT / "configs" / "setup-mode-matrix-policy.json")
        report = smm.validate_setup_mode_matrix_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        phrase = policy["policy"]["boundary_phrase"]
        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "onboarding" / "SETUP_MODES.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
        ]:
            self.assertIn(phrase, path.read_text(encoding="utf-8"))
        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertIn("- [x] Linux host mode: native services + local paths.", backlog)
        self.assertIn("- [x] macOS dev mode: non-privileged developer path for repo validation and light workflows.", backlog)
        self.assertIn("- [x] VM mode: Ubuntu/Debian VM as the recommended no-risk onboarding path.", backlog)
        self.assertIn("- [x] Docker dev mode: explicitly marked as development/test only, not the full production NoemaForge path.", backlog)

    def test_setup_mode_boundary_is_closed_in_canonical_docs(self) -> None:
        phrase = smm.load_policy(ROOT / "configs" / "setup-mode-matrix-policy.json")["policy"]["boundary_phrase"]
        closed_line = f"- [x] {phrase} {self.CLOSURE}"
        legacy_open_line = f"- {phrase}"
        for path in [ROOT / "docs" / "TODO.md", ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md"]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(closed_line, text)
            self.assertNotIn(legacy_open_line, text)
        changelog = (ROOT / "docs" / "history" / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(phrase, changelog)
        self.assertIn("setup-mode-matrix-core", changelog)


if __name__ == "__main__":
    unittest.main()

