#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_noemashell_lite_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test NoemaShell Lite discoverability through registry and canonical docs.
Inputs: Unified Registry, NoemaShell Lite policy and canonical documentation files.
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

import noemashell_lite_runtime as nslr
import unified_registry_runtime as urr


class NoemaShellLiteQATests(unittest.TestCase):
    def test_noemashell_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:noemashell-lite-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/noemashell-lite-policy.json", pack["refs"])
        self.assertIn("src/noemashell_lite_runtime.py", pack["refs"])
        self.assertIn("tests/test_noemashell_lite_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:noemashell-lite-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/noemashell-lite-policy.json", pipeline["refs"])
        self.assertIn("src/noemashell_lite_runtime.py", pipeline["refs"])

    def test_noemashell_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = nslr.load_policy(ROOT / "configs" / "noemashell-lite-policy.json")
        self.assertEqual("NoemaShellLitePolicy", policy["kind"])
        self.assertEqual("primary_operator_shell", policy["policy"]["activation_state"])
        self.assertIn("safe_mode", policy["policy"]["primary_surfaces"])

        report = nslr.validate_noemashell_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [p for p in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
        ] if p.exists()]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Make NoemaShell Lite the primary operator shell", text)
            self.assertIn("NoemaShell Lite", text)
            self.assertIn("resource budgets", text)

        for path in [p for p in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ] if p.exists()]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("noemashell-lite-core", text)
            self.assertIn("primary operator shell", text)


if __name__ == "__main__":
    unittest.main()

