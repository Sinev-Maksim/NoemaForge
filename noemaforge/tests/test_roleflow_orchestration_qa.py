#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_roleflow_orchestration_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test RoleFlow discoverability through registry and canonical docs.
Inputs: Unified Registry, RoleFlow policy and canonical documentation files.
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

import roleflow_orchestration_runtime as rfor
import unified_registry_runtime as urr


class RoleFlowOrchestrationQATests(unittest.TestCase):
    def test_roleflow_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:roleflow-orchestration-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/roleflow-orchestration-policy.json", pack["refs"])
        self.assertIn("src/roleflow_orchestration_runtime.py", pack["refs"])
        self.assertIn("tests/test_roleflow_orchestration_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:roleflow-orchestration-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/roleflow-orchestration-policy.json", pipeline["refs"])
        self.assertIn("src/roleflow_orchestration_runtime.py", pipeline["refs"])

    def test_roleflow_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = rfor.load_policy(ROOT / "configs" / "roleflow-orchestration-policy.json")
        self.assertEqual("RoleFlowPolicy", policy["kind"])
        self.assertEqual("protected_orchestration", policy["policy"]["activation_state"])
        self.assertIn("approval_edges", policy["policy"]["required_flow_features"])

        report = rfor.validate_roleflow_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [p for p in [
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
        ] if p.exists()]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Formalize `RoleFlow` / `orchestration_graph` schema", text)
            self.assertIn("RoleFlow Orchestration", text)
            self.assertIn("rollback", text)

        for path in [p for p in [
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ] if p.exists()]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("roleflow-orchestration-core", text)
            self.assertIn("baton payloads", text)


if __name__ == "__main__":
    unittest.main()

