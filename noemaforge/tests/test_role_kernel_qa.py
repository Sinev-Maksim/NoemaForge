#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_role_kernel_qa.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Role Kernel discoverability through registry and canonical docs.
Inputs: Unified Registry, Role Kernel policy and canonical documentation files.
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

import role_kernel_runtime as rkr
import unified_registry_runtime as urr


class RoleKernelQATests(unittest.TestCase):
    def test_role_kernel_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:role-kernel-active-nn-core:0.32.0")
        self.assertIsNotNone(pack)
        self.assertIn("configs/role-kernel-policy.json", pack["refs"])
        self.assertIn("src/role_kernel_runtime.py", pack["refs"])
        self.assertIn("tests/test_role_kernel_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.31.13.alpha-patched1"]
        self.assertIn("eval-pack:role-kernel-active-nn-core:0.32.0", pipeline["eval_pack_refs"])
        self.assertIn("configs/role-kernel-policy.json", pipeline["refs"])
        self.assertIn("src/role_kernel_runtime.py", pipeline["refs"])

    def test_role_kernel_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = rkr.load_policy(ROOT / "configs" / "role-kernel-policy.json")
        self.assertEqual("RoleKernelPolicy", policy["kind"])
        self.assertEqual("protected_kernel", policy["policy"]["activation_state"])
        self.assertEqual(1, policy["policy"]["active_nn_manager"]["max_active_heavy_workers"])

        report = rkr.validate_role_kernel_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Keep base install focused on four default roles", text)
            self.assertIn("Role Kernel", text)
            self.assertIn("one-heavy-worker", text)

        for path in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("role-kernel-active-nn-core", text)
            self.assertIn("one-heavy-worker", text)


if __name__ == "__main__":
    unittest.main()

