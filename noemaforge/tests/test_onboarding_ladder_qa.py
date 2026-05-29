#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_onboarding_ladder_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test onboarding ladder discoverability through registry, docs and TODO.
Inputs: Unified Registry, onboarding ladder policy and canonical documentation files.
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

import onboarding_ladder_runtime as olr


class OnboardingLadderQATests(unittest.TestCase):
    CLOSURE = "Closed by `onboarding-ladder-core`"

    def test_pack_is_registered_and_attached_to_firstboot_pipeline(self) -> None:
        registry = json.loads((ROOT / "configs" / "unified-registry.json").read_text(encoding="utf-8"))
        entries = {f"{item['kind']}:{item['id']}:{item['version']}": item for item in registry["entries"]}
        pack_ref = "eval-pack:onboarding-ladder-core:0.32.1"
        pack = entries.get(pack_ref)
        self.assertIsNotNone(pack)
        self.assertIn("docs/onboarding/QUICKSTART_VM.md", pack["refs"])
        self.assertIn("docs/onboarding/PRODUCTION_INSTALL_TRIXIE.md", pack["refs"])
        self.assertIn("docs/onboarding/MVP_OPERATOR_GUIDE.md", pack["refs"])
        self.assertIn("docs/TODO.md", pack["refs"])
        self.assertIn("docs/reference/PROJECT_CONTEXT.md", pack["refs"])
        self.assertIn("tests/test_onboarding_ladder_performance.py", pack["refs"])
        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn(pack_ref, pipeline["eval_pack_refs"])
        self.assertIn("configs/onboarding-ladder-policy.json", pipeline["refs"])
        self.assertIn("src/onboarding_ladder_runtime.py", pipeline["refs"])
        self.assertIn("docs/onboarding/PRODUCTION_INSTALL_TRIXIE.md", pipeline["refs"])

    def test_public_docs_and_todo_capture_onboarding_boundary(self) -> None:
        policy = olr.load_policy(ROOT / "configs" / "onboarding-ladder-policy.json")
        report = olr.validate_onboarding_ladder_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        phrase = policy["policy"]["boundary_phrase"]
        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "onboarding" / "QUICKSTART_VM.md",
            ROOT / "docs" / "onboarding" / "SETUP_MODES.md",
            ROOT / "docs" / "onboarding" / "PRODUCTION_INSTALL_TRIXIE.md",
            ROOT / "docs" / "onboarding" / "MVP_OPERATOR_GUIDE.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
        ]:
            self.assertIn(phrase, path.read_text(encoding="utf-8"))
        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertIn("- [x] `README.md` -> 5-minute overview.", backlog)
        self.assertIn("- [x] `QUICKSTART_VM.md` -> first success path.", backlog)
        self.assertIn("- [x] `SETUP_MODES.md` -> host / VM / docker-dev differences.", backlog)
        self.assertIn("- [x] `PRODUCTION_INSTALL_TRIXIE.md` -> only after the quickstart path exists.", backlog)

    def test_onboarding_ladder_boundary_is_closed_in_canonical_docs(self) -> None:
        phrase = olr.load_policy(ROOT / "configs" / "onboarding-ladder-policy.json")["policy"]["boundary_phrase"]
        closed_line = f"- [x] {phrase} {self.CLOSURE}"
        legacy_open_line = f"- {phrase}"
        for path in [ROOT / "docs" / "TODO.md", ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md"]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(closed_line, text)
            self.assertNotIn(legacy_open_line, text)
        changelog = (ROOT / "docs" / "history" / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(phrase, changelog)
        self.assertIn("onboarding-ladder-core", changelog)


if __name__ == "__main__":
    unittest.main()

