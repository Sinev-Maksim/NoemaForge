#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_nologin_recovery_readiness_qa.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: QA-test registry and docs coverage for target `/run/nologin` recovery readiness.
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

import nologin_recovery_readiness_runtime as nrr
import unified_registry_runtime as urr

OPEN_TODO = "- [ ] Confirm `/run/nologin` is cleared after recovery on NoemaForge."
PACK_ID = "nologin-recovery-readiness-core"
BLOCKED_STATE = "blocked_until_target_nologin_recovery_evidence"


class NologinRecoveryReadinessQATests(unittest.TestCase):
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
        self.assertIn("configs/nologin-recovery-readiness-policy.json", pack["refs"])
        self.assertIn("contracts/nologin_recovery_readiness.schema.json", pack["refs"])
        self.assertIn("src/nologin_recovery_readiness_runtime.py", pack["refs"])
        self.assertEqual(BLOCKED_STATE, pack["metadata"]["todo_state"])
        task = entries.get("task:first-start-model-selection:0.32.1")
        self.assertIsNotNone(task)
        self.assertIn(f"eval-pack:{PACK_ID}:0.32.1", task["eval_pack_refs"])

    def test_docs_record_blocker_without_closing_target_item(self) -> None:
        report = nrr.validate_nologin_recovery_readiness_policy(nrr.load_policy())
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
            ROOT / "docs" / "wiki" / "first-start" / "full-composite-real-launch-0.31.13.alpha-patched1.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(PACK_ID, text, str(path))
            self.assertIn(BLOCKED_STATE, text, str(path))

    def test_runtime_never_executes_live_recovery_commands(self) -> None:
        text = (ROOT / "src" / "nologin_recovery_readiness_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn("import subprocess", text)
        self.assertNotIn("os.system", text)
        self.assertNotIn("Popen", text)


if __name__ == "__main__":
    unittest.main()

