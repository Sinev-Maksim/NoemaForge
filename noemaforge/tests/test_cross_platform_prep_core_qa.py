#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_cross_platform_prep_core_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test cross-platform prep core discoverability through registry, docs and TODO.
Inputs: Unified Registry, cross-platform prep policy and canonical documentation files.
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

import cross_platform_prep_core_runtime as cpp


class CrossPlatformPrepCoreQATests(unittest.TestCase):
    CLOSURE = "Closed by `cross-platform-prep-core`"

    def test_pack_is_registered_and_attached_to_firstboot_pipeline(self) -> None:
        registry = json.loads((ROOT / "configs" / "unified-registry.json").read_text(encoding="utf-8"))
        entries = {f"{item['kind']}:{item['id']}:{item['version']}": item for item in registry["entries"]}
        pack_ref = "eval-pack:cross-platform-prep-core:0.32.1"
        pack = entries.get(pack_ref)
        self.assertIsNotNone(pack)
        self.assertIn("tools/prep/noemaforge_prep_core.py", pack["refs"])
        self.assertIn("tests/test_cross_platform_prep_core_performance.py", pack["refs"])
        self.assertIn("docs/TODO.md", pack["refs"])
        self.assertIn("docs/reference/PROJECT_CONTEXT.md", pack["refs"])
        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn(pack_ref, pipeline["eval_pack_refs"])
        self.assertIn("tools/prep/noemaforge_prep_core.py", pipeline["refs"])
        self.assertIn("src/cross_platform_prep_core_runtime.py", pipeline["refs"])

    def test_public_docs_and_todo_capture_cross_platform_boundary(self) -> None:
        policy = cpp.load_policy(ROOT / "configs" / "cross-platform-prep-core-policy.json")
        report = cpp.validate_cross_platform_prep_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        phrase = policy["policy"]["boundary_phrase"]
        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
        ]:
            self.assertIn(phrase, path.read_text(encoding="utf-8"))
        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertIn("- [x] Treat `tools/prep/*.py` as the source of truth.", backlog)
        self.assertIn("- [x] Add shell wrappers for Linux/macOS matching the Windows commands.", backlog)

    def test_cross_platform_prep_boundary_is_closed_in_canonical_docs(self) -> None:
        phrase = cpp.load_policy(ROOT / "configs" / "cross-platform-prep-core-policy.json")["policy"]["boundary_phrase"]
        closed_line = f"- [x] {phrase} {self.CLOSURE}"
        legacy_open_line = f"- {phrase}"
        for path in [ROOT / "docs" / "TODO.md", ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md"]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(closed_line, text)
            self.assertNotIn(legacy_open_line, text)
        changelog = (ROOT / "docs" / "history" / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(phrase, changelog)
        self.assertIn("cross-platform-prep-core", changelog)


if __name__ == "__main__":
    unittest.main()

