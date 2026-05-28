#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_production_gui_installer_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test registry and docs coverage for the production GUI installer contract.
Inputs: Unified Registry and canonical documentation files.
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

import production_gui_installer_runtime as pgi


class ProductionGuiInstallerQATests(unittest.TestCase):
    def test_registry_attaches_production_gui_installer_eval_pack(self) -> None:
        policy = pgi.load_policy(ROOT / "configs" / "production-gui-installer-policy.json")
        report = pgi.validate_production_gui_installer_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        registry = json.loads((ROOT / "configs" / "unified-registry.json").read_text(encoding="utf-8"))
        pack = next(
            entry for entry in registry["entries"]
            if entry.get("kind") == "eval-pack" and entry.get("id") == "production-gui-installer-core"
        )
        self.assertIn("configs/production-gui-installer-policy.json", pack["refs"])
        self.assertIn("src/production_gui_installer_runtime.py", pack["refs"])
        self.assertIn("timer_driven_gui_autostart", pack["metadata"]["metrics"])

    def test_canonical_docs_close_production_gui_installer_item(self) -> None:
        closed_item = "[x] Production-grade GUI installer."
        open_item = "[ ] Production-grade GUI installer."
        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("production-gui-installer-core", text, str(path))

        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        todo = (ROOT / "docs" / "TODO.md").read_text(encoding="utf-8")
        self.assertIn(closed_item, backlog)
        self.assertNotIn(open_item, backlog)
        self.assertIn(closed_item, todo)


if __name__ == "__main__":
    unittest.main()
