#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_media_wiki_patch_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate media wiki patch runtime behaviour.
Inputs: Workspace media wiki patch policy and synthetic media patch manifests.
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

import media_wiki_patch_runtime as mwpr
import wiki_patch_runtime as wpr


class MediaWikiPatchRuntimeTests(unittest.TestCase):
    def test_workspace_media_wiki_patch_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "media-wiki-patch-policy.json"
        report = mwpr.validate_media_wiki_patch_policy(
            mwpr.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(2, report["metrics"]["required_flags"])
        self.assertEqual(4, report["metrics"]["required_outputs"])
        self.assertEqual(1, report["metrics"]["passing_scenarios"])

    def test_wiki_patch_create_carries_media_delta_and_generated_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source_root = tmp / "source"
            wiki_repo = tmp / "wiki"
            out_dir = tmp / "patch"
            (source_root / "docs" / "wiki" / "media").mkdir(parents=True)
            (wiki_repo / "docs" / "wiki" / "media").mkdir(parents=True)
            (source_root / "docs" / "wiki" / "media" / "capabilities.md").write_text("# media capabilities\n", encoding="utf-8")
            media_report = tmp / "media-report.json"
            artifact_manifest = tmp / "artifacts.json"
            media_report.write_text(json.dumps(mwpr.synthetic_media_capability_delta()), encoding="utf-8")
            artifact_manifest.write_text(json.dumps(mwpr.synthetic_artifact_manifest(2)), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                wpr.main([
                    "--root",
                    str(ROOT),
                    "create",
                    "--wiki-repo",
                    str(wiki_repo),
                    "--source-root",
                    str(source_root),
                    "--title",
                    "Media capability patch",
                    "--include",
                    "docs/wiki/media/capabilities.md",
                    "--media-capability-report",
                    str(media_report),
                    "--artifact-manifest",
                    str(artifact_manifest),
                    "--out-dir",
                    str(out_dir),
                    "--json",
                ])
            result = json.loads(stdout.getvalue())
            manifest = json.loads((out_dir / "wiki_patch_manifest.json").read_text(encoding="utf-8"))
            policy = mwpr.load_policy(ROOT / "configs" / "media-wiki-patch-policy.json")

            self.assertTrue(result["ok"], result)
            self.assertTrue((out_dir / "media_capability_delta.json").exists())
            self.assertTrue((out_dir / "generated_artifacts.json").exists())
            self.assertTrue(mwpr.validate_media_patch_manifest(manifest, policy)["ok"])
            functional = (out_dir / "functional_delta.md").read_text(encoding="utf-8")
            self.assertIn("Media capability delta", functional)
            self.assertIn("Generated artifacts", functional)

    def test_missing_generated_artifacts_breaks_manifest_contract(self) -> None:
        policy = mwpr.load_policy(ROOT / "configs" / "media-wiki-patch-policy.json")
        result = mwpr.validate_media_patch_manifest(
            {"media_capability_delta": {"present": True, "path": "media_capability_delta.json"}},
            policy,
        )

        self.assertFalse(result["ok"])
        self.assertIn("manifest_generated_artifacts_missing", result["failures"])


if __name__ == "__main__":
    unittest.main()
