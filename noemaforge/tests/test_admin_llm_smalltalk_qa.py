#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_llm_smalltalk_qa.py
Zone: gui/control-plane
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Admin LLM smalltalk registry and documentation coverage.
Inputs: Unified Registry, admin-llm-smalltalk policy and canonical documentation.
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

import admin_llm_smalltalk_runtime as als
import unified_registry_runtime as urr

CLOSURE = "Closed by `admin-llm-smalltalk-core`"
TODO_ITEM = "Add LLM-backed conversational Admin path for smalltalk while preserving deterministic control-plane routing."


class AdminLLMSmalltalkQATests(unittest.TestCase):
    def test_pack_is_registered_with_runtime_refs(self) -> None:
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
        pack = entries.get("eval-pack:admin-llm-smalltalk-core:0.32.2")
        self.assertIsNotNone(pack)
        self.assertIn("configs/admin-llm-smalltalk-policy.json", pack["refs"])
        self.assertIn("contracts/admin_llm_smalltalk.schema.json", pack["refs"])
        self.assertIn("src/admin_llm_smalltalk_runtime.py", pack["refs"])
        self.assertIn("src/admin_gui_server.py", pack["refs"])
        self.assertIn("tests/test_admin_llm_smalltalk_performance.py", pack["refs"])

    def test_docs_and_changelog_record_closed_smalltalk_item(self) -> None:
        policy = als.load_policy(ROOT / "configs" / "admin-llm-smalltalk-policy.json")
        report = als.validate_admin_llm_smalltalk_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertEqual(0, backlog.count(f"- [ ] {TODO_ITEM}"))
        self.assertGreaterEqual(backlog.count(f"- [x] {TODO_ITEM}"), 1)
        self.assertIn(CLOSURE, backlog)

        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("admin-llm-smalltalk-core", text, str(path))
            self.assertIn("conversation_backend", text, str(path))
            self.assertIn(CLOSURE, text, str(path))


if __name__ == "__main__":
    unittest.main()

