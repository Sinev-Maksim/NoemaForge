#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_backlog_status_legend_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test backlog status legend contract discoverability through registry and docs.
Inputs: Unified Registry, backlog status legend policy and canonical documentation files.
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

import backlog_status_legend_runtime as bslr
import unified_registry_runtime as urr

CLOSURE = "Closed by `backlog-status-legend-core`"


class BacklogStatusLegendQATests(unittest.TestCase):
    def test_pack_is_registered_with_docs_refs(self) -> None:
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
        pack = entries.get("eval-pack:backlog-status-legend-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/backlog-status-legend-policy.json", pack["refs"])
        self.assertIn("contracts/backlog_status_legend.schema.json", pack["refs"])
        self.assertIn("src/backlog_status_legend_runtime.py", pack["refs"])
        self.assertIn("tests/test_backlog_status_legend_runtime.py", pack["refs"])
        self.assertIn("tests/test_backlog_status_legend_performance.py", pack["refs"])
        self.assertIn("docs/backlog/ROADMAP_AND_TODO.md", pack["refs"])

    def test_docs_and_changelog_record_closed_status_legend_item(self) -> None:
        policy = bslr.load_policy(ROOT / "configs" / "backlog-status-legend-policy.json")
        report = bslr.validate_backlog_status_legend_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertNotIn("- [ ] planned", backlog)
        self.assertIn("- `planned`: open/not started.", backlog)
        self.assertIn(CLOSURE, backlog)

        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("backlog-status-legend-core", text, str(path))
            self.assertIn("status legend", text, str(path))
            self.assertIn(CLOSURE, text, str(path))


if __name__ == "__main__":
    unittest.main()

