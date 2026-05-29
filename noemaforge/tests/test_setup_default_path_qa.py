#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_setup_default_path_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Setup Default Path discoverability through registry, docs and TODO.
Inputs: Unified Registry, Setup Default Path policy and canonical documentation files.
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

import setup_default_path_runtime as sdp
import unified_registry_runtime as urr


class SetupDefaultPathQATests(unittest.TestCase):
    CLOSURE = "Closed by `setup-default-path-core`"

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
        pack = entries.get("eval-pack:setup-default-path-core:0.32.2")
        self.assertIsNotNone(pack)
        self.assertIn("configs/setup-default-path-policy.json", pack["refs"])
        self.assertIn("setup.sh", pack["refs"])
        self.assertIn("docs/onboarding/QUICKSTART_VM.md", pack["refs"])
        self.assertIn("tests/test_setup_default_path_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.2"]
        self.assertIn("eval-pack:setup-default-path-core:0.32.2", pipeline["eval_pack_refs"])
        self.assertIn("configs/setup-default-path-policy.json", pipeline["refs"])
        self.assertIn("src/setup_default_path_runtime.py", pipeline["refs"])

    def test_public_docs_and_todo_capture_setup_default_path_boundary(self) -> None:
        policy = sdp.load_policy(ROOT / "configs" / "setup-default-path-policy.json")
        phrase = policy["policy"]["boundary_phrase"]
        validation = sdp.validate_setup_default_path_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(validation["ok"], validation["failures"])

        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "onboarding" / "QUICKSTART_VM.md",
            ROOT / "docs" / "onboarding" / "SETUP_MODES.md",
        ]:
            self.assertIn(phrase, path.read_text(encoding="utf-8"))
        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertIn("[x] Define a single default path: `git clone` or release unpack -> `./setup.sh` -> reboot -> use.", backlog)
        self.assertIn("[x] Keep VM mode as the first-class onboarding target for new users.", backlog)

    def test_setup_default_path_boundary_is_closed_in_canonical_docs(self) -> None:
        phrase = sdp.load_policy(ROOT / "configs" / "setup-default-path-policy.json")["policy"]["boundary_phrase"]
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
        self.assertIn("setup-default-path-core", changelog)


if __name__ == "__main__":
    unittest.main()

