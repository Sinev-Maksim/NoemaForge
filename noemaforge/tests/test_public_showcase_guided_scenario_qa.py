#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_public_showcase_guided_scenario_qa.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test public showcase guided scenario registry and documentation coverage.
Inputs: Unified Registry, public showcase policy and canonical documentation.
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

import public_showcase_guided_scenario_runtime as psg
import unified_registry_runtime as urr

CLOSURE = "Closed by `public-showcase-guided-scenario-core`"
DECIDE_ITEM = "Decide the one public “бантик”: either a small live backend adapter demo or a polished Admin GUI guided scenario."
PICK_ITEM = "Pick one public “бантик”: recommended option is a polished Admin GUI guided scenario using existing planning flows, unless a small live backend adapter is ready without destabilizing release."


class PublicShowcaseGuidedScenarioQATests(unittest.TestCase):
    def test_pack_is_registered_with_gui_refs(self) -> None:
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
        pack = entries.get("eval-pack:public-showcase-guided-scenario-core:0.32.2")
        self.assertIsNotNone(pack)
        self.assertIn("configs/public-showcase-guided-scenario-policy.json", pack["refs"])
        self.assertIn("src/public_showcase_guided_scenario_runtime.py", pack["refs"])
        self.assertIn("src/admin_gui_server.py", pack["refs"])
        self.assertIn("templates/pipeline-dashboard/app.js", pack["refs"])

    def test_docs_and_changelog_record_closed_showcase_choice(self) -> None:
        policy = psg.load_policy(ROOT / "configs" / "public-showcase-guided-scenario-policy.json")
        report = psg.validate_public_showcase_guided_scenario_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertEqual(0, backlog.count(f"- [ ] {DECIDE_ITEM}"))
        self.assertEqual(0, backlog.count(f"- [ ] {PICK_ITEM}"))
        self.assertGreaterEqual(backlog.count(f"- [x] {DECIDE_ITEM}"), 2)
        self.assertGreaterEqual(backlog.count(f"- [x] {PICK_ITEM}"), 2)
        self.assertIn(CLOSURE, backlog)

        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("public-showcase-guided-scenario-core", text, str(path))
            self.assertIn("polished_admin_gui_guided_scenario", text, str(path))
            self.assertIn(CLOSURE, text, str(path))


if __name__ == "__main__":
    unittest.main()

