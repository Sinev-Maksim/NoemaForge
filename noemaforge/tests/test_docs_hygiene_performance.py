#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_docs_hygiene_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-21
Purpose: Performance-test docs hygiene validation on a synthetic Markdown-heavy and file-heavy tree.
Inputs: Temporary local fixture with hundreds of Markdown files.
Outputs: unittest assertions only.
Side effects: Creates and removes a temporary fixture directory.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import os
import shutil
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
TMP_ROOT = ROOT / "tests" / "_tmp_docs_hygiene_perf"
sys.path.insert(0, str(ROOT / "src"))

import docs_hygiene_runtime as dhr


class DocsHygienePerformanceTests(unittest.TestCase):
    def tearDown(self) -> None:
        if TMP_ROOT.exists():
            shutil.rmtree(TMP_ROOT)

    @unittest.skipIf(sys.platform == "win32", "wall-time threshold tuned for Linux/BigBro-BOS")
    def test_synthetic_markdown_tree_validates_under_budget(self) -> None:
        source_policy = dhr.load_policy(ROOT / "configs" / "docs-hygiene-policy.json")
        payload = copy.deepcopy(source_policy)
        project = TMP_ROOT / "project"
        package = project / "noemaforge"
        docs_wiki = package / "docs" / "wiki" / "generated"
        docs_wiki.mkdir(parents=True, exist_ok=True)

        todo_label = payload["policy"]["required_checked_todo_items"][0]["label"]
        payload["policy"]["required_checked_todo_items"] = [{"file": "noemaforge/docs/TODO.md", "label": todo_label}]
        payload["refs"] = list(payload["policy"]["required_canonical_files"])

        for ref in payload["policy"]["required_canonical_files"]:
            path = project / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# canonical\n", encoding="utf-8")
        (package / "docs" / "TODO.md").write_text(f"- [x] {todo_label}\n", encoding="utf-8")

        for index in range(600):
            (docs_wiki / f"page-{index:04d}.md").write_text("# generated\n\nBody.\n", encoding="utf-8")
            (package / "docs" / "wiki" / "generated" / f"artifact-{index:04d}.json").write_text('{"ok": true}\n', encoding="utf-8")

        started = time.perf_counter()
        report = dhr.validate_docs_hygiene_policy(payload, project_root=project, package_root=package)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"])
        self.assertGreaterEqual(report["metrics"]["markdown_files"], 600)
        self.assertGreaterEqual(report["metrics"]["active_files"], 1200)
        self.assertEqual(0, report["metrics"]["active_file_readability_failures"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
