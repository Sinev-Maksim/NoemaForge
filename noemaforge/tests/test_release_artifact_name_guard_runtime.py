#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_release_artifact_name_guard_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Unit-test release artifact name guard validation and failure reporting.
Inputs: Active policy plus synthetic project fixtures.
Outputs: unittest assertions only.
Side effects: Creates and removes temporary fixture directories.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import os
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
TMP_ROOT = PROJECT_ROOT / "_tmp_rang"
sys.path.insert(0, str(ROOT / "src"))

import release_artifact_name_guard_runtime as rang


def _fixture_policy(project: Path) -> dict:
    package = project / "noemaforge"
    docs = package / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    for ref in [
        "history/CHANGELOG.md",
        "TODO.md",
        "README.md",
        "reference/PROJECT_CONTEXT.md",
        "backlog/ROADMAP_AND_TODO.md",
        "wiki/prelaunch/prelaunch-tooling.md",
    ]:
        path = docs / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "release-artifact-name-guard-core history/CHANGELOG.md parallel release-note Closed by `release-artifact-name-guard-core`\n",
            encoding="utf-8",
        )
    runtime = package / "src" / "release_artifact_name_guard_runtime.py"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(
        "canonical_release_history_only forbidden_filename_patterns _scan_forbidden_file_names\n",
        encoding="utf-8",
    )
    return {
        "apiVersion": rang.API_VERSION,
        "kind": rang.POLICY_KIND,
        "id": "release-artifact-name-guard-core",
        "version": "0.32.1",
        "status": "stable",
        "policy": {
            "mode": "offline_contract",
            "activation_state": "canonical_release_history_only",
            "require_registry_attachment": True,
            "require_docs_and_changelog_refs": True,
            "require_no_live_host_dependency": True,
            "canonical_changelog_ref": "noemaforge/docs/history/CHANGELOG.md",
            "allowed_exact_refs": ["noemaforge/docs/history/CHANGELOG.md"],
            "forbidden_filename_patterns": ["CHANGELOG_*", "RELEASE_NOTES_*", "VERIFICATION_REPORT_*", "deep-research-report*", "source-report*"],
            "excluded_dir_names": ["trash", "__pycache__", ".pytest_cache"],
            "required_runtime_scripts": ["noemaforge/src/release_artifact_name_guard_runtime.py"],
            "required_runtime_tokens": ["canonical_release_history_only", "forbidden_filename_patterns", "_scan_forbidden_file_names"],
            "required_docs": [
                "noemaforge/docs/README.md",
                "noemaforge/docs/TODO.md",
                "noemaforge/docs/reference/PROJECT_CONTEXT.md",
                "noemaforge/docs/backlog/ROADMAP_AND_TODO.md",
                "noemaforge/docs/wiki/prelaunch/prelaunch-tooling.md",
                "noemaforge/docs/history/CHANGELOG.md",
            ],
            "required_doc_tokens": ["release-artifact-name-guard-core", "history/CHANGELOG.md", "parallel release-note"],
        },
        "refs": [
            "noemaforge/src/release_artifact_name_guard_runtime.py",
            "noemaforge/docs/README.md",
            "noemaforge/docs/history/CHANGELOG.md",
        ],
    }


class ReleaseArtifactNameGuardRuntimeTests(unittest.TestCase):
    def tearDown(self) -> None:
        if TMP_ROOT.exists():
            shutil.rmtree(TMP_ROOT)

    def test_active_policy_validates_current_tree(self) -> None:
        policy = rang.load_policy(ROOT / "configs" / "release-artifact-name-guard-policy.json")
        report = rang.validate_release_artifact_name_guard_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(0, report["metrics"]["forbidden_filename_hits"])
        self.assertEqual("noemaforge/docs/history/CHANGELOG.md", report["canonical_changelog_ref"])

    def test_forbidden_parallel_release_artifact_names_fail_but_trash_is_ignored(self) -> None:
        project = TMP_ROOT / "project"
        policy = _fixture_policy(project)
        (project / "CHANGELOG_2026-05-21.md").write_text("# extra\n", encoding="utf-8")
        (project / "noemaforge" / "docs" / "history" / "RELEASE_NOTES_shadow.md").write_text("# extra\n", encoding="utf-8")
        trash = project / "trash"
        trash.mkdir(parents=True, exist_ok=True)
        (trash / "VERIFICATION_REPORT_ignored.md").write_text("# ignored\n", encoding="utf-8")

        report = rang.validate_release_artifact_name_guard_policy(policy, project_root=project, package_root=project / "noemaforge")

        self.assertFalse(report["ok"])
        self.assertEqual(2, report["metrics"]["forbidden_filename_hits"])
        self.assertTrue(any("CHANGELOG_2026-05-21.md" in item for item in report["failures"]))
        self.assertFalse(any("VERIFICATION_REPORT_ignored.md" in item for item in report["failures"]))

    def test_gate_evidence_reflects_guard_status(self) -> None:
        project = TMP_ROOT / "evidence-project"
        policy = _fixture_policy(project)
        report = rang.validate_release_artifact_name_guard_policy(policy, project_root=project, package_root=project / "noemaforge")
        evidence = rang.release_artifact_name_guard_report_to_gate_evidence(
            report,
            artifact_uri="reports/release-artifact-name-guard.json",
        )
        self.assertEqual("passed", evidence["status"])
        self.assertEqual("release_artifact_name_guard", evidence["gate"])
        self.assertEqual(0, evidence["metrics"]["forbidden_filename_hits"])

    def test_missing_doc_token_is_reported(self) -> None:
        project = TMP_ROOT / "doc-token-project"
        policy = _fixture_policy(project)
        bad_policy = copy.deepcopy(policy)
        bad_policy["policy"]["required_doc_tokens"].append("missing-token-for-test")

        report = rang.validate_release_artifact_name_guard_policy(bad_policy, project_root=project, package_root=project / "noemaforge")

        self.assertFalse(report["ok"])
        self.assertIn("required_doc_token_missing:missing-token-for-test", report["failures"])


if __name__ == "__main__":
    unittest.main()
