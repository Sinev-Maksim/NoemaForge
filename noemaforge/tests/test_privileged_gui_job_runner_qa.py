#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_privileged_gui_job_runner_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test documentation, roadmap, changelog and registry coverage for privileged GUI jobs.
Inputs: Canonical docs, unified registry and privileged GUI job-runner policy.
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

import privileged_gui_job_runner as pgr


class PrivilegedGuiJobRunnerQATests(unittest.TestCase):
    def test_registry_attaches_privileged_gui_job_runner_eval_pack(self) -> None:
        policy = pgr.load_policy(ROOT / "configs" / "privileged-gui-job-runner-policy.json")
        report = pgr.validate_privileged_gui_job_runner_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        registry = json.loads((ROOT / "configs" / "unified-registry.json").read_text(encoding="utf-8"))
        pack = next(
            entry for entry in registry["entries"]
            if entry.get("kind") == "eval-pack" and entry.get("id") == "privileged-gui-job-runner-core"
        )
        self.assertIn("configs/privileged-gui-job-runner-policy.json", pack["refs"])
        self.assertIn("src/privileged_gui_job_runner.py", pack["refs"])
        self.assertIn("share/polkit-1/actions/org.noemaforge.privileged-jobs.policy", pack["refs"])
        self.assertIn("polkit_approval_required", pack["metadata"]["metrics"])
        self.assertIn("model_selection_continue", pack["metadata"]["metrics"])
        self.assertIn("vault_reinventory", pack["metadata"]["metrics"])

    def test_canonical_docs_record_closed_approved_gui_runner_items(self) -> None:
        closed_items = [
            "[x] Convert GUI epoch apply request into privileged, polkit-mediated local action after safety review.",
            "[x] Add polkit/root job-runner for approved privileged GUI jobs after alpha.",
        ]
        open_items = [
            "[ ] Convert GUI epoch apply request into privileged, polkit-mediated local action after safety review.",
            "[ ] Add polkit/root job-runner for approved privileged GUI jobs after alpha.",
        ]
        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("privileged-gui-job-runner-core", text, str(path))
            self.assertIn("polkit_approval_required", text, str(path))

        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        todo = (ROOT / "docs" / "TODO.md").read_text(encoding="utf-8")
        for closed_item in closed_items:
            self.assertIn(closed_item, backlog)
            self.assertIn(closed_item, todo)
        for open_item in open_items:
            self.assertNotIn(open_item, backlog)

    def test_changelog_records_privileged_gui_job_runner(self) -> None:
        changelog = (ROOT / "docs" / "history" / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("privileged-gui-job-runner-core", changelog)
        self.assertIn("polkit_approval_required", changelog)
        self.assertIn("org.noemaforge.privileged-jobs.run", changelog)


if __name__ == "__main__":
    unittest.main()
