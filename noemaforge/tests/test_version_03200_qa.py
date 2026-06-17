#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_version_03200_qa.py
Zone: release/package
Version: 0.33.0
Created: 2026-05-20
Modified: 2026-06-17
Purpose: Validate the 0.33.0 version promotion across active release surfaces.
Inputs: Workspace version files, active runtime constants, setup front door and package metadata.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = PACKAGE_ROOT.parent
# SOT_VERSION — the release version, derived dynamically from the canonical
# VERSION source of truth. The 0.33.0 promotion (2026-06-17) folded the former
# PROMOTED_BASELINE (the non-canonical surfaces: active config versions, the CLI
# echo, first-run-audit, root release/manifest metadata) into SOT_VERSION, so all
# active release surfaces are now asserted against the single source of truth.
# Never pin SOT_VERSION to a literal.
SOT_VERSION = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
EXPECTED_INSTALLER = "install_noemaforge_mvp.sh"
EXPECTED_UNINSTALLER = "uninstall_noemaforge_mvp.sh"
OLD_ACTIVE_INSTALLER = "install_noemaforge_0.32.1_mvp.sh"


CONFIG_VERSION_FILES = [
    "alpha-feature-coverage.json",
    "autostart-llm-policy.json",
    "code-qa-team.json",
    "gui-shell-policy.json",
    "inactivity-policy.json",
    "low-hanging-fruits.json",
    "media-pipeline-catalog.json",
    "module-test-matrix.json",
    "multimodal-backends-policy.json",
    "persona-catalog.json",
    "pipeline-editor-policy.json",
    "pipeline-pattern-catalog.json",
    "pipeline-ui-catalog.json",
    "review-routing-policy.json",
    "runtime-device-policy.json",
    "self-improvement-policy.json",
    "selftest-case-catalog.json",
    "selftest-telemetry-policy.json",
    "task-categories.json",
    "team-member-policy.json",
    "telemetry-policy.json",
    "test-matrix.json",
]


RUNTIME_CONSTANT_FILES = [
    "admin_gui_server.py",
    "admin_runtime.py",
    "code_qa_runtime.py",
    "dev_team_runtime.py",
    "first_start_summary.py",
    "intent_router_eval.py",
    "model_evolution_runtime.py",
    "model_selection_runtime.py",
    "pipeline_runtime.py",
    "selftest_runtime.py",
    "team_member_runtime.py",
    "wiki_patch_runtime.py",
]


class Version03200QATests(unittest.TestCase):
    def test_canonical_version_files_are_promoted(self) -> None:
        version_files = [
            PROJECT_ROOT / "VERSION",
            PACKAGE_ROOT / "VERSION",
            PROJECT_ROOT / "docs" / "VERSION",
            PACKAGE_ROOT / "docs" / "VERSION",
        ]
        for path in version_files:
            with self.subTest(path=path):
                self.assertEqual(SOT_VERSION, path.read_text(encoding="utf-8").strip())

    def test_release_manifest_metadata_is_promoted(self) -> None:
        release = json.loads((PROJECT_ROOT / "release.json").read_text(encoding="utf-8"))

        self.assertEqual(SOT_VERSION, release["version"])
        self.assertEqual(f"noemaforge_{SOT_VERSION}_prelaunch", release["package"])
        self.assertTrue(release["summary"].startswith(f"NoemaForge {SOT_VERSION}:"))

        # MANIFEST.json is release evidence: generated (untracked) at pre-release
        # only. Its version-bearing fields are derived from release.json by
        # ci/regen_evidence.py, so they track the assertions above by construction.
        manifest_path = PROJECT_ROOT / "MANIFEST.json"
        if not manifest_path.is_file():
            self.skipTest("release-tier: MANIFEST.json is generated at pre-release only")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(SOT_VERSION, manifest["runtime_base_version"])
        self.assertEqual(f"noemaforge_{SOT_VERSION}_prelaunch", manifest["package_name"])

    def test_runtime_constants_and_cli_fallback_are_promoted(self) -> None:
        # 0.32.2: runtime files use centralised import, not hardcoded RUNTIME_VERSION.
        for rel in RUNTIME_CONSTANT_FILES:
            path = PACKAGE_ROOT / "src" / rel
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertIn("from noemaforge_version import RUNTIME_VERSION", text)
                self.assertNotIn(f'RUNTIME_VERSION = "0.32.1"', text)

        cli = (PACKAGE_ROOT / "bin" / "noemaforge").read_text(encoding="utf-8")
        first_run_audit = (PACKAGE_ROOT / "tools" / "prep" / "noemaforge-first-run-audit.sh").read_text(encoding="utf-8")
        self.assertIn(f'echo "{SOT_VERSION}"', cli)
        self.assertIn(f'VERSION="{SOT_VERSION}"', first_run_audit)

    def test_active_config_versions_are_promoted(self) -> None:
        for rel in CONFIG_VERSION_FILES:
            path = PACKAGE_ROOT / "configs" / rel
            with self.subTest(path=path):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(SOT_VERSION, payload.get("version"))

    def test_setup_and_dry_run_policy_point_to_promoted_installer(self) -> None:
        setup = (PROJECT_ROOT / "setup.sh").read_text(encoding="utf-8")
        policy = json.loads((PACKAGE_ROOT / "configs" / "package-dry-run-validation-policy.json").read_text(encoding="utf-8"))
        example = json.loads((PROJECT_ROOT / "prelaunch" / "governance" / "package_dry_run_validation.example.json").read_text(encoding="utf-8"))

        self.assertTrue((PROJECT_ROOT / EXPECTED_INSTALLER).exists())
        self.assertTrue((PROJECT_ROOT / EXPECTED_UNINSTALLER).exists())
        self.assertIn(EXPECTED_INSTALLER, setup)
        self.assertIn(EXPECTED_INSTALLER, policy["policy"]["required_scripts"]["installer"])
        self.assertIn(EXPECTED_UNINSTALLER, policy["policy"]["required_scripts"]["uninstall"])
        self.assertIn(EXPECTED_INSTALLER, example["scenarios"][0]["refs"])
        self.assertIn(EXPECTED_INSTALLER, example["scenarios"][0]["expected"]["syntax_checks"])
        self.assertNotIn(f'exec "$PKG_DIR/{OLD_ACTIVE_INSTALLER}"', setup)


if __name__ == "__main__":
    unittest.main()
