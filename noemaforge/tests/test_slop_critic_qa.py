#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_slop_critic_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Slop Critic discoverability through registry and canonical docs.
Inputs: Unified Registry, Slop Critic policy and canonical documentation files.
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

import slop_critic_runtime as scr
import unified_registry_runtime as urr


class SlopCriticQATests(unittest.TestCase):
    def test_slop_critic_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:slop-critic-governance-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/slop-critic-policy.json", pack["refs"])
        self.assertIn("src/slop_critic_runtime.py", pack["refs"])
        self.assertIn("tests/test_slop_critic_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:slop-critic-governance-core:0.32.1", pipeline["eval_pack_refs"])

    def test_slop_critic_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = scr.load_policy(ROOT / "configs" / "slop-critic-policy.json")
        self.assertEqual("SlopCriticPolicy", policy["kind"])
        self.assertEqual({"genericity", "repetition", "unsupportedness", "provenance_gap"}, set(policy["policy"]["bands"]))
        self.assertTrue(policy["policy"]["advisory_by_default"])

        report = scr.validate_slop_critic_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Add Slop_Score and Critic_Stack as advisory quality gates", text)
            self.assertIn("[x] Add `Slop_Score` and `Critic_Stack` as advisory quality layers", text)

        for path in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Slop_Score / Critic_Stack contract", text)
            self.assertIn("slop-critic-governance-core", text)


if __name__ == "__main__":
    unittest.main()

