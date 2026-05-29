#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_multios_runtime_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: QA-test MultiOS runtime discoverability through registry and canonical docs.
Inputs: Unified Registry, MultiOS runtime policy and canonical documentation files.
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
sys.path.insert(0, str(PROJECT_ROOT))

import multios_runtime_contract as mrc
import unified_registry_runtime as urr
from noemaforge.runtime.registry import load_runtime_policy


class MultiOSRuntimeQATests(unittest.TestCase):
    def test_multios_runtime_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:multios-runtime-host-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/noemaforge.runtime.yaml", pack["refs"])
        self.assertIn("runtime/os_probe.py", pack["refs"])
        self.assertIn("tests/test_multios_runtime_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:multios-runtime-host-core:0.32.1", pipeline["eval_pack_refs"])

    def test_multios_runtime_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = load_runtime_policy(ROOT / "configs" / "noemaforge.runtime.yaml")
        self.assertEqual("NoemaForgeRuntimePolicy", policy["kind"])
        profile_ids = {profile["id"] for profile in policy["profiles"]}
        self.assertEqual(
            {"linux-reference-systemd", "windows-control-host", "macos-control-host", "remote-http-runtime"},
            profile_ids,
        )

        report = mrc.validate_multios_runtime_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Add runtime abstraction layer", text)
            self.assertIn("[x] Add `configs/noemaforge.runtime.yaml`", text)
            self.assertIn("[x] Add smoke tests for Linux, Windows and macOS host detection", text)

        for path in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("MultiOS runtime host contract", text)
            self.assertIn("multios-runtime-host-core", text)


if __name__ == "__main__":
    unittest.main()

