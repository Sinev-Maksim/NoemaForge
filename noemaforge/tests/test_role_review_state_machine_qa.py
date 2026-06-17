#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_role_review_state_machine_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test Admin/Surgeon/Scary state-machine discoverability through registry and docs.
Inputs: Unified Registry, role review state-machine policy and canonical documentation files.
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

import role_review_state_machine_runtime as rrsm
import unified_registry_runtime as urr


class RoleReviewStateMachineQATests(unittest.TestCase):
    def test_role_review_state_machine_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:role-review-state-machine-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/role-review-state-machine-policy.json", pack["refs"])
        self.assertIn("contracts/role_review_state_machine.schema.json", pack["refs"])
        self.assertIn("configs/roleflow-orchestration-policy.json", pack["refs"])
        self.assertIn("src/role_review_state_machine_runtime.py", pack["refs"])
        self.assertIn("tests/test_role_review_state_machine_performance.py", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:role-review-state-machine-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/role-review-state-machine-policy.json", pipeline["refs"])
        self.assertIn("src/role_review_state_machine_runtime.py", pipeline["refs"])

    def test_public_docs_and_todo_capture_role_review_boundary(self) -> None:
        policy = rrsm.load_policy(ROOT / "configs" / "role-review-state-machine-policy.json")
        phrase = policy["policy"]["boundary_phrase"]
        validation = rrsm.validate_role_review_state_machine_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(validation["ok"], validation["failures"])

        _existing_docs = [p for p in [
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "docs" / "README.md",
            ROOT / "docs" / "README.md",
            PROJECT_ROOT / "TODO.md",
            ROOT / "TODO.md",
            PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ] if p.exists()]
        assert _existing_docs, "no candidate documentation file exists"
        for path in _existing_docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn(phrase, text)
        self.assertIn("[x] Admin/Surgeon/Scary role-flow runtime state machine.", (PROJECT_ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

