#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_wiki_patch_commit_helper_runtime.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate reviewed wiki-patch branch/commit helper invariants.
Inputs: Workspace wiki-patch commit-helper policy and synthetic patch bundles.
Outputs: unittest assertions only.
Side effects: Temporary files under unittest temp directories only.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import production_ai_contracts as pac
import selftest_runtime as strt
import wiki_patch_commit_helper_runtime as wpchr


def make_patch_bundle(tmp: Path, patch_id: str = "wiki_patch_example") -> tuple[Path, Path]:
    patch_dir = tmp / "patch"
    wiki_repo = tmp / "wiki"
    (patch_dir / "payload" / "docs").mkdir(parents=True)
    wiki_repo.mkdir()
    (wiki_repo / ".git").mkdir()
    (patch_dir / "payload" / "docs" / "page.md").write_text("# page\n", encoding="utf-8")
    (patch_dir / "apply.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (patch_dir / "wiki_patch_manifest.json").write_text(json.dumps({"patch_id": patch_id}), encoding="utf-8")
    return patch_dir, wiki_repo


class WikiPatchCommitHelperRuntimeTests(unittest.TestCase):
    def test_workspace_wiki_patch_commit_helper_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "wiki-patch-commit-helper-policy.json"
        validation = wpchr.validate_wiki_patch_commit_helper_policy(
            wpchr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(1, validation["metrics"]["scenarios"])
        self.assertEqual(1, validation["metrics"]["passing_scenarios"])

        gate = pac.evaluate_gate(
            {"change_id": "wiki-patch-commit-helper-core", "domain": "pipeline"},
            wpchr.wiki_patch_commit_helper_report_to_gate_evidence(validation, artifact_uri="reports/wiki-patch-commit-helper.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_commit_plan_requires_review_and_never_pushes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            patch_dir, wiki_repo = make_patch_bundle(Path(raw))
            plan = strt.build_wiki_patch_commit_plan(
                patch_dir,
                wiki_repo,
                branch="noemaforge/wiki/wiki_patch_example",
                reviewed_by="operator",
                review_id="review-001",
            )
            script = Path(plan["artifacts"]["script"]).read_text(encoding="utf-8")

        self.assertTrue(plan["no_push"])
        self.assertTrue(plan["review"]["required"])
        self.assertEqual("operator", plan["review"]["reviewed_by"])
        self.assertIn("git -C", script)
        self.assertIn("commit -F", script)
        self.assertNotIn("git push", script)

    def test_commit_plan_command_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            patch_dir, wiki_repo = make_patch_bundle(tmp, patch_id="cli_patch")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                strt.main([
                    "wiki-patch",
                    "commit-plan",
                    "--patch-dir",
                    str(patch_dir),
                    "--wiki-repo",
                    str(wiki_repo),
                    "--branch",
                    "noemaforge/wiki/cli_patch",
                    "--reviewed-by",
                    "operator",
                    "--review-id",
                    "review-002",
                    "--json",
                ])
            plan = json.loads(stdout.getvalue())

            self.assertEqual("WikiPatchCommitPlan", plan["kind"])
            self.assertTrue(Path(plan["artifacts"]["plan"]).exists())
            self.assertTrue(Path(plan["artifacts"]["script"]).exists())
            self.assertTrue(Path(plan["artifacts"]["commit_message"]).exists())
            self.assertEqual("review-002", plan["review"]["review_id"])

    def test_missing_review_breaks_plan_builder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            patch_dir, wiki_repo = make_patch_bundle(Path(raw))
            with self.assertRaisesRegex(ValueError, "reviewed_by_required"):
                strt.build_wiki_patch_commit_plan(patch_dir, wiki_repo, branch="noemaforge/wiki/missing-review", reviewed_by="")


if __name__ == "__main__":
    unittest.main()
