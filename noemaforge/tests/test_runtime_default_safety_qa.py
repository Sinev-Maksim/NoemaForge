#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_runtime_default_safety_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test runtime default safety discoverability through registry and docs.
Inputs: Unified Registry, runtime-default-safety policy and canonical documentation files.
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

import runtime_default_safety_runtime as rdsr
import unified_registry_runtime as urr


class RuntimeDefaultSafetyQATests(unittest.TestCase):
    def test_runtime_default_safety_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:runtime-default-safety-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/runtime-default-safety-policy.json", pack["refs"])
        self.assertIn("contracts/runtime_default_safety.schema.json", pack["refs"])
        self.assertIn("configs/autostart-llm-policy.json", pack["refs"])
        self.assertIn("src/runtime_default_safety_runtime.py", pack["refs"])
        self.assertIn("tests/test_runtime_default_safety_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:runtime-default-safety-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/runtime-default-safety-policy.json", pipeline["refs"])
        self.assertIn("src/runtime_default_safety_runtime.py", pipeline["refs"])

    def test_runtime_default_safety_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = rdsr.load_policy(ROOT / "configs" / "runtime-default-safety-policy.json")
        self.assertEqual("RuntimeDefaultSafetyPolicy", policy["kind"])
        self.assertEqual("runtime_default_single_llm_and_manual_heavy_boot", policy["policy"]["activation_state"])
        self.assertIn("single_active_llm_default", policy["policy"]["required_outputs"])

        validation = rdsr.validate_runtime_default_safety_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(validation["ok"], validation["failures"])

        for path in [p for p in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
        ] if p.exists()]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Do not enable parallel heavy model runtime by default.", text)
            self.assertIn("[x] Do not auto-start heavy GPU LLM backends at boot.", text)
            self.assertIn("runtime-default-safety-core", text)

        for path in [p for p in [
            PROJECT_ROOT / "docs" / "README.md",
            ROOT / "docs" / "README.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ] if p.exists()]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("runtime-default-safety-core", text)
            self.assertIn("max_active_llms=1", text)


if __name__ == "__main__":
    unittest.main()

