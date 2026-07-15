#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_docs_hygiene_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-21
Purpose: Validate docs hygiene policy enforcement for canonical Markdown, changelog layout and active-file readability.
Inputs: Workspace docs hygiene policy and temporary broken fixtures.
Outputs: unittest assertions only.
Side effects: Creates and removes temporary fixture directories.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import docs_hygiene_runtime as dhr
import production_ai_contracts as pac


class DocsHygieneRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="noemaforge_docs_hygiene_")
        self.tmp_root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_workspace_docs_hygiene_policy_validates_with_legacy_warnings(self) -> None:
        policy_path = ROOT / "configs" / "docs-hygiene-policy.json"
        report = dhr.validate_docs_hygiene_policy(
            dhr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(0, report["metrics"]["missing_required_canonical_files"])
        self.assertEqual(0, report["metrics"]["outside_policy_markdown_files"])
        self.assertEqual(0, report["metrics"]["forbidden_markdown_files"])
        self.assertEqual(0, report["metrics"]["forbidden_active_text_hits"])
        self.assertEqual(0, report["metrics"]["parallel_changelog_files"])
        self.assertEqual(0, report["metrics"]["active_file_readability_failures"])
        self.assertEqual(16, report["metrics"]["todo_items_checked"])
        self.assertEqual(4, report["metrics"]["legacy_root_markdown_files"])
        self.assertEqual("passed", report["checks"][0]["status"])
        self.assertEqual("passed", report["checks"][1]["status"])

        gate = pac.evaluate_gate(
            {"change_id": "docs-hygiene-policy", "domain": "pipeline"},
            dhr.docs_hygiene_report_to_gate_evidence(report, artifact_uri="reports/docs-hygiene.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_policy_blocks_new_root_markdown_and_parallel_changelog(self) -> None:
        policy_path = ROOT / "configs" / "docs-hygiene-policy.json"
        payload = copy.deepcopy(dhr.load_policy(policy_path))
        project = self.tmp_root / "project"
        package = project / "noemaforge"
        for folder in [
            package / "docs" / "history",
            package / "docs" / "source_reports",
            package / "docs" / "wiki",
        ]:
            folder.mkdir(parents=True, exist_ok=True)

        required_text = "# placeholder\n"
        for ref in payload["policy"]["required_canonical_files"]:
            path = project / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(required_text, encoding="utf-8")
        (package / "docs" / "TODO.md").write_text("- [ ] Add Unified Registry for model, prompt, retriever, reranker, tool-policy, pipeline, persona, task, epoch and eval-pack versions.\n", encoding="utf-8")
        (project / "NOTES.md").write_text("# drift\n", encoding="utf-8")
        (project / "RELEASE_NOTES.md").write_text("# parallel\n", encoding="utf-8")
        (package / "docs" / "EXTRA.md").write_text("# extra\n", encoding="utf-8")
        (package / "docs" / "source_reports" / "raw.md").write_text("# raw\n", encoding="utf-8")

        report = dhr.validate_docs_hygiene_policy(
            payload,
            project_root=project,
            package_root=package,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("root_markdown_not_allowed:NOTES.md", report["failures"])
        self.assertIn("docs_root_markdown_not_allowed:noemaforge/docs/EXTRA.md", report["failures"])
        self.assertIn("forbidden_markdown_prefix:noemaforge/docs/source_reports/raw.md", report["failures"])
        self.assertIn("parallel_changelog_file:RELEASE_NOTES.md", report["failures"])
        self.assertIn(
            "todo_item_not_checked:noemaforge/docs/TODO.md:Add Unified Registry for model, prompt, retriever, reranker, tool-policy, pipeline, persona, task, epoch and eval-pack versions.",
            report["failures"],
        )

    def test_policy_blocks_forbidden_active_text(self) -> None:
        policy_path = ROOT / "configs" / "docs-hygiene-policy.json"
        payload = copy.deepcopy(dhr.load_policy(policy_path))
        project = self.tmp_root / "project"
        package = project / "noemaforge"
        package_docs = package / "docs"
        for folder in [
            package_docs / "history",
            package_docs / "reference",
            package_docs / "wiki",
        ]:
            folder.mkdir(parents=True, exist_ok=True)

        label = payload["policy"]["required_checked_todo_items"][0]["label"]
        payload["policy"]["required_checked_todo_items"] = [{"file": "noemaforge/docs/TODO.md", "label": label}]
        payload["refs"] = list(payload["policy"]["required_canonical_files"])
        for ref in payload["policy"]["required_canonical_files"]:
            path = project / ref
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# canonical\n", encoding="utf-8")
        (package_docs / "TODO.md").write_text(f"- [x] {label}\n", encoding="utf-8")
        token = "BigBro" + "-BOS"
        (package_docs / "wiki" / "forbidden-host.md").write_text(f"# target\n\n{token}\n", encoding="utf-8")

        report = dhr.validate_docs_hygiene_policy(
            payload,
            project_root=project,
            package_root=package,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertEqual(1, report["metrics"]["forbidden_active_text_hits"])
        self.assertIn(
            f"forbidden_active_text:noemaforge/docs/wiki/forbidden-host.md:3:{token}",
            report["failures"],
        )

    def test_active_file_readability_blocks_stale_entries(self) -> None:
        project = self.tmp_root / "project"
        project.mkdir(parents=True, exist_ok=True)
        stale = project / "prelaunch" / "ghost.py"

        result = dhr._validate_active_file_readability([stale], project_root=project)

        self.assertEqual(
            ["unreadable_active_file:prelaunch/ghost.py:FileNotFoundError"],
            result["failures"],
        )
        self.assertEqual([{"path": "prelaunch/ghost.py", "error": "FileNotFoundError"}], result["unreadable"])

    def test_root_docs_are_active_for_forbidden_text_gate(self) -> None:
        project = self.tmp_root / "project"
        docs = project / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        token = "BigBro" + "-BOS"
        active = docs / "legacy.md"
        active.write_text(f"# legacy\n\n{token}\n", encoding="utf-8")

        result = dhr._validate_forbidden_active_text(
            dhr._iter_active_files(project),
            project_root=project,
            forbidden_tokens=[token],
        )

        self.assertEqual(1, len(result["hits"]))
        self.assertIn(f"forbidden_active_text:docs/legacy.md:3:{token}", result["failures"])

    def test_agent_task_markdown_is_not_active_release_docs(self) -> None:
        project = self.tmp_root / "project"
        task_dir = project / ".noemaforge-agent-tasks" / "token-aware-0330-v3"
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "task.md").write_text("# local task\n", encoding="utf-8")

        self.assertEqual([], dhr._iter_markdown_files(project))
        self.assertEqual([], dhr._iter_active_files(project))

    def test_policy_blocks_missing_required_refs(self) -> None:
        policy_path = ROOT / "configs" / "docs-hygiene-policy.json"
        payload = copy.deepcopy(dhr.load_policy(policy_path))
        payload["policy"]["required_canonical_files"].append("docs/missing/CANONICAL.md")
        payload["refs"].append("noemaforge/docs/missing/CANONICAL.md")

        report = dhr.validate_docs_hygiene_policy(
            payload,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("missing_required_canonical_file:docs/missing/CANONICAL.md", report["failures"])
        self.assertIn("missing_ref:prelaunch-docs-hygiene:noemaforge/docs/missing/CANONICAL.md", report["failures"])

    def test_cli_summary_returns_compact_json(self) -> None:
        policy_path = ROOT / "configs" / "docs-hygiene-policy.json"
        report = dhr.validate_docs_hygiene_policy(
            dhr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )
        summary = {
            "kind": "DocsHygieneSummary",
            "ok": report["ok"],
            "metrics": report["metrics"],
        }

        self.assertEqual("DocsHygieneSummary", summary["kind"])
        self.assertTrue(summary["ok"])
        self.assertIn("markdown_files", summary["metrics"])


if __name__ == "__main__":
    unittest.main()
