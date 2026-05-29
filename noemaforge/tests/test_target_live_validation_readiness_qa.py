#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_target_live_validation_readiness_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test registry and docs coverage for target live validation readiness.
Inputs: Unified Registry, readiness policy and canonical documentation.
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

import target_live_validation_readiness_runtime as tlv
import unified_registry_runtime as urr

OPEN_TODO = "- [ ] Real NoemaForge live validation of NVIDIA/GDM/LLM services."
PACK_ID = "target-live-validation-readiness-core"
BLOCKED_STATE = "blocked_until_target_machine_evidence"


class TargetLiveValidationReadinessQATests(unittest.TestCase):
    def test_pack_is_registered_with_contract_refs(self) -> None:
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
        pack = entries.get(f"eval-pack:{PACK_ID}:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/target-live-validation-readiness-policy.json", pack["refs"])
        self.assertIn("contracts/target_live_validation_readiness.schema.json", pack["refs"])
        self.assertIn("src/target_live_validation_readiness_runtime.py", pack["refs"])

    def test_docs_record_blocker_without_closing_live_validation(self) -> None:
        report = tlv.validate_target_live_validation_readiness_policy(tlv.load_policy())
        self.assertTrue(report["ok"], report["failures"])
        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertIn(OPEN_TODO, backlog)
        self.assertIn(PACK_ID, backlog)
        self.assertIn(BLOCKED_STATE, backlog)
        self.assertNotIn(f"{OPEN_TODO} Closed by `{PACK_ID}`", backlog)
        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "wiki" / "first-start" / "full-composite-real-launch-0.32.1.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(PACK_ID, text, str(path))
            self.assertIn(BLOCKED_STATE, text, str(path))

    def test_runtime_never_executes_live_commands(self) -> None:
        text = (ROOT / "src" / "target_live_validation_readiness_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn("import subprocess", text)
        self.assertNotIn("os.system", text)
        self.assertNotIn("Popen", text)


if __name__ == "__main__":
    unittest.main()

