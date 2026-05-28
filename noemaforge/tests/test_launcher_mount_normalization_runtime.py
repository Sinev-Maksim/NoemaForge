#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_launcher_mount_normalization_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate launcher mount path normalization for Trixie firstboot.
Inputs: Synthetic legacy and canonical launcher paths.
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
sys.path.insert(0, str(ROOT / "src"))

import runtime_safety


class LauncherMountNormalizationRuntimeTests(unittest.TestCase):
    def test_runtime_safety_canonicalizes_legacy_share_paths_without_io(self) -> None:
        cases = {
            "/mnt/brainos-share": "/mnt/noemaforge-share",
            "/mnt/brainos-share/Vault/models": "/mnt/noemaforge-share/Vault/models",
            "/mnt/brainos-share/brainos-lab": "/mnt/noemaforge-share/noemaforge-lab",
            "/mnt/brainos-share/brainos-lab/data/Vault": "/mnt/noemaforge-share/noemaforge-lab/data/Vault",
            "/mnt/noemaforge-share/noemaforge-lab/data/Vault": "/mnt/noemaforge-share/noemaforge-lab/data/Vault",
        }
        for source, expected in cases.items():
            self.assertEqual(expected, runtime_safety.canonicalize_noemaforge_path(source))

    def test_firstboot_launcher_normalizes_all_operator_paths_before_scan(self) -> None:
        report = runtime_safety.normalize_launcher_paths(
            share_root="/mnt/brainos-share",
            vault_root="/mnt/brainos-share/brainos-lab/data/Vault",
            shortlist_file="/mnt/brainos-share/Vault/manifests/noemaforge-firstboot-shortlist.txt",
        )

        self.assertTrue(report["changed"], report)
        self.assertEqual("/mnt/noemaforge-share", report["share_root"])
        self.assertEqual("/mnt/noemaforge-share/noemaforge-lab/data/Vault", report["vault_root"])
        self.assertEqual("/mnt/noemaforge-share/Vault/manifests/noemaforge-firstboot-shortlist.txt", report["shortlist_file"])
        self.assertEqual("/mnt/noemaforge-share", report["canonical_share_root"])

    def test_firstboot_launcher_normalization_is_idempotent_for_canonical_paths(self) -> None:
        first = runtime_safety.normalize_launcher_paths(
            share_root="/mnt/noemaforge-share",
            vault_root="/mnt/noemaforge-share/noemaforge-lab/data/Vault",
            shortlist_file="/mnt/noemaforge-share/Vault/manifests/noemaforge-firstboot-shortlist.txt",
        )
        second = runtime_safety.normalize_launcher_paths(
            share_root=first["share_root"],
            vault_root=first["vault_root"],
            shortlist_file=first["shortlist_file"],
        )

        self.assertFalse(first["changed"], first)
        self.assertFalse(second["changed"], second)
        self.assertEqual(first["share_root"], second["share_root"])
        self.assertEqual(first["vault_root"], second["vault_root"])


if __name__ == "__main__":
    unittest.main()
