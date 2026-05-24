#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_default_model_runtime_policy_qa.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test docs and registry coverage for the default model runtime policy.
Inputs: Workspace TODO, roadmap, changelog, README, project context and unified registry.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import default_model_runtime_policy as dmrp


class DefaultModelRuntimePolicyQATests(unittest.TestCase):
    def test_registry_attaches_default_model_runtime_eval_pack(self) -> None:
        policy = dmrp.load_policy(ROOT / "configs" / "default-model-runtime-policy.json")
        report = dmrp.validate_default_model_runtime_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        registry = json.loads((ROOT / "configs" / "unified-registry.json").read_text(encoding="utf-8"))
        entries = registry["entries"]
        pack = next(
            entry for entry in entries
            if entry.get("kind") == "eval-pack" and entry.get("id") == "default-model-runtime-policy-core"
        )
        self.assertIn("configs/default-model-runtime-policy.json", pack["refs"])
        self.assertIn("src/default_model_runtime_policy.py", pack["refs"])
        self.assertIn("tests/test_default_model_runtime_policy_runtime.py", pack["refs"])
        self.assertIn("cpu_safe_always_on_with_gpu_on_demand", pack["metadata"]["metrics"])

    def test_canonical_docs_record_closed_default_policy_item(self) -> None:
        closed_item = "[x] Decide default always-on CPU-safe model policy vs GPU-on-demand policy."
        open_item = "[ ] Decide default always-on CPU-safe model policy vs GPU-on-demand policy."
        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("default-model-runtime-policy-core", text, str(path))
            self.assertIn("cpu_safe_always_on_with_gpu_on_demand", text, str(path))

        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertIn(closed_item, backlog)
        self.assertNotIn(open_item, backlog)
        self.assertIn("CPU-safe default and explicit GPU-on-demand", backlog)

    def test_changelog_records_the_single_canonical_release_entry(self) -> None:
        changelog = (ROOT / "docs" / "history" / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("default-model-runtime-policy-core", changelog)
        self.assertIn("CPU-safe default and explicit GPU-on-demand", changelog)
        self.assertIn("runtime-device-policy.json", changelog)


if __name__ == "__main__":
    unittest.main()
