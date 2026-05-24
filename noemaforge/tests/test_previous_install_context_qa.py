#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_previous_install_context_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test previous-install context boundary discoverability through registry and docs.
Inputs: Unified Registry, previous install context policy and canonical documentation files.
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

import previous_install_context_runtime as pic
import unified_registry_runtime as urr

CLOSURE = "Closed by `previous-install-context-core`"


class PreviousInstallContextQATests(unittest.TestCase):
    def test_context_pack_is_registered_and_attached_to_firstboot_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:previous-install-context-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/previous-install-context-policy.json", pack["refs"])
        self.assertIn("contracts/previous_install_context.schema.json", pack["refs"])
        self.assertIn("src/previous_install_context_runtime.py", pack["refs"])
        self.assertIn("src/runtime_safety.py", pack["refs"])
        self.assertIn("tests/test_previous_install_context_runtime.py", pack["refs"])
        self.assertIn("docs/TODO.md", pack["refs"])
        self.assertIn("docs/reference/PROJECT_CONTEXT.md", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:previous-install-context-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/previous-install-context-policy.json", pipeline["refs"])
        self.assertIn("src/previous_install_context_runtime.py", pipeline["refs"])

    def test_policy_docs_and_changelog_record_closed_previous_install_item(self) -> None:
        policy = pic.load_policy(ROOT / "configs" / "previous-install-context-policy.json")
        report = pic.validate_previous_install_context_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        item = "Confirm previous installation backup/migration context is not active runtime."
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
            self.assertIn("previous-install-context-core", text, str(path))
            self.assertIn("backup/migration context", text, str(path))
            self.assertIn(CLOSURE, text, str(path))


if __name__ == "__main__":
    unittest.main()

