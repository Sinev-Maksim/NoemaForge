#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_firstboot_progress_qa.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test firstboot progress discoverability through registry, CLI and docs.
Inputs: Unified Registry, firstboot progress policy, CLI wrapper and canonical docs.
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

import firstboot_progress_runtime as fbp
import unified_registry_runtime as urr


class FirstbootProgressQATests(unittest.TestCase):
    CLOSURE = "Closed by `firstboot-progress-view-core`"

    def test_progress_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:firstboot-progress-view-core:0.32.0")
        self.assertIsNotNone(pack)
        self.assertIn("configs/firstboot-progress-view-policy.json", pack["refs"])
        self.assertIn("src/firstboot_progress_runtime.py", pack["refs"])
        self.assertIn("docs/TODO.md", pack["refs"])
        self.assertIn("tests/test_firstboot_progress_performance.py", pack["refs"])
        pipeline = entries["pipeline:firstboot-model-selection:0.31.13.alpha-patched1"]
        self.assertIn("eval-pack:firstboot-progress-view-core:0.32.0", pipeline["eval_pack_refs"])
        self.assertIn("src/firstboot_progress_runtime.py", pipeline["refs"])

    def test_cli_docs_and_todo_capture_progress_boundary(self) -> None:
        policy = fbp.load_policy(ROOT / "configs" / "firstboot-progress-view-policy.json")
        phrase = policy["policy"]["boundary_phrase"]
        cli_text = (ROOT / "bin" / "noemaforge").read_text(encoding="utf-8")
        self.assertIn("noemaforge first-start progress", cli_text)
        self.assertIn("progress|watch|tui", cli_text)
        report = fbp.validate_firstboot_progress_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
        ]:
            self.assertIn(phrase, path.read_text(encoding="utf-8"))
        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertIn("[x] Keep JSON status/events, but also add a human-readable TUI/CLI progress view.", backlog)
        self.assertIn("[x] Add a final summary with next actions.", backlog)

    def test_firstboot_progress_boundary_is_closed_in_canonical_docs(self) -> None:
        phrase = fbp.load_policy(ROOT / "configs" / "firstboot-progress-view-policy.json")["policy"]["boundary_phrase"]
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
        self.assertIn("firstboot-progress-view-core", changelog)


if __name__ == "__main__":
    unittest.main()

