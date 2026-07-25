#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_cross_platform_prep_core_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate cross-platform prep core runtime behavior.
Inputs: Cross-platform prep policy, Python prep core and temporary Lab/Vault fixtures.
Outputs: unittest assertions only.
Side effects: TemporaryDirectory fixtures only.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "prep"))

import cross_platform_prep_core_runtime as cpp
import noemaforge_prep_core as prep_core


class CrossPlatformPrepCoreRuntimeTests(unittest.TestCase):
    def test_windows_release_validation_wrappers_default_to_official_vault_path(self) -> None:
        export_wrapper = (ROOT / "tools" / "windows" / "Export-NoemaForge-E-Vault-Metadata.ps1").read_text(encoding="utf-8")
        compare_wrapper = (ROOT / "tools" / "windows" / "Export-NoemaForge-E-Compare-Metadata.ps1").read_text(encoding="utf-8")
        check_wrapper = (ROOT / "tools" / "windows" / "Check-NoemaForge-VaultRoot.ps1").read_text(encoding="utf-8")

        canonical_vault = r"E:\noemaforge-lab\data\Vault"
        canonical_out = r"E:\noemaforge-lab\data\Vault\manifests\noemaforge-metadata-export"
        canonical_check_out = r"E:\noemaforge-lab\data\Vault\manifests\noemaforge-metadata-export\diagnose"

        self.assertIn(f"[string]$VaultRoot = '{canonical_vault}'", export_wrapper)
        self.assertIn(f"[string]$OutDir = '{canonical_out}'", export_wrapper)
        self.assertIn(f"[string]$LabVaultRoot = '{canonical_vault}'", compare_wrapper)
        self.assertIn(f"[string]$OutDir = '{canonical_out}'", compare_wrapper)
        self.assertIn(f"[string]$VaultRoot = '{canonical_vault}'", check_wrapper)
        self.assertIn(f"[string]$OutDir = '{canonical_check_out}'", check_wrapper)
        self.assertNotIn("[string]$OutDir = 'E:\\Vault\\manifests\\noemaforge-metadata-export'", export_wrapper)
        self.assertNotIn("[string]$OutDir = 'E:\\Vault\\manifests\\noemaforge-metadata-export'", compare_wrapper)

    def test_windows_metadata_docs_default_to_official_vault_output_path(self) -> None:
        operator_guide = (ROOT / "docs" / "operations" / "OPERATOR_GUIDE.md").read_text(encoding="utf-8")
        roadmap = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")

        stale_output_arg = "-OutDir 'E:\\Vault\\manifests\\noemaforge-metadata-export'"
        canonical_output_arg = "-OutDir 'E:\\noemaforge-lab\\data\\Vault\\manifests\\noemaforge-metadata-export'"

        self.assertIn(canonical_output_arg, operator_guide)
        self.assertIn(canonical_output_arg, roadmap)
        self.assertNotIn(stale_output_arg, operator_guide)
        self.assertNotIn(stale_output_arg, roadmap)

    def test_workspace_policy_validates(self) -> None:
        policy = cpp.load_policy(ROOT / "configs" / "cross-platform-prep-core-policy.json")
        report = cpp.validate_cross_platform_prep_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])
        self.assertGreaterEqual(report["metrics"]["surface_refs"], 12)
        self.assertGreaterEqual(report["metrics"]["boundary_refs"], 8)

    def test_firstboot_staging_runs_without_windows(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nfg-prep-core-") as td:
            lab = Path(td) / "noemaforge-lab"
            vault_inbox = lab / "data" / "Vault" / "inbox"
            library_inbox = lab / "data" / "Library" / "inbox"
            vault_inbox.mkdir(parents=True)
            library_inbox.mkdir(parents=True)
            (vault_inbox / "candidate.gguf").write_bytes(b"gguf")
            (library_inbox / "note.md").write_text("# note\n", encoding="utf-8")

            plan = prep_core.firstboot_stage(ROOT, lab, model_profile="minimal", auto_manifest=True, dry_run=False)

            self.assertFalse(plan["windows_required"])
            self.assertFalse(plan["auto_download"])
            self.assertEqual("minimal", plan["model_profile"])
            self.assertTrue((lab / "outbox" / "prep" / "firstboot_staging_plan.json").exists())
            self.assertTrue((lab / "data" / "Vault" / "vault_index.sqlite").exists())
            self.assertTrue((lab / "data" / "Vault" / "model_registry.seed.json").exists())
            self.assertTrue((lab / "data" / "Library" / "library_index.sqlite").exists())

    def test_metadata_export_and_cli_verify_seed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nfg-vault-meta-") as td:
            vault = Path(td) / "Vault"
            out = Path(td) / "out"
            (vault / "models-gguf").mkdir(parents=True)
            (vault / "models-gguf" / "tiny.gguf").write_bytes(b"gguf")
            summary = prep_core.export_vault_metadata(ROOT, vault, out, run_scan_vault=True, full_hash=False)

            self.assertEqual("noemaforge.disk_e_metadata/v1", summary["apiVersion"])
            self.assertEqual(1, summary["counts"]["models:models-gguf"])
            self.assertTrue((out / "vault.disk_e.metadata.json").exists())
            self.assertTrue((out / "vault.disk_e.summary.txt").exists())
            self.assertTrue((out / "vault.disk_e.roots.csv").exists())

        raw = subprocess.check_output(
            [sys.executable, str(ROOT / "tools" / "prep" / "noemaforge_prep_core.py"), "verify-seed", "--repo-root", str(ROOT)],
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        payload = json.loads(raw)
        self.assertTrue(payload["ok"], payload["missing"])


if __name__ == "__main__":
    unittest.main()
