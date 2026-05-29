#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_unified_registry_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate Unified Registry runtime reference and eval-pack checks.
Inputs: Temporary registry fixtures and the workspace registry file.
Outputs: unittest assertions only.
Side effects: Creates and removes temporary fixture directories.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import unified_registry_runtime as urr


class UnifiedRegistryRuntimeTests(unittest.TestCase):
    def test_workspace_unified_registry_refs_and_eval_packs_validate(self) -> None:
        registry_path = ROOT / "configs" / "unified-registry.json"
        report = urr.validate_unified_registry(
            urr.load_registry(registry_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=registry_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(0, report["metrics"]["missing_refs"])
        self.assertEqual(0, report["metrics"]["missing_eval_pack_refs"])
        self.assertEqual([], report["missing_required_kinds"])
        self.assertGreaterEqual(report["metrics"]["entries"], 10)
        self.assertIn("eval-pack:production-ai-gate-smoke:0.32.1", report["active_registry_refs"])

    def test_registry_validation_blocks_missing_ref_and_eval_pack_ref(self) -> None:
        with tempfile.TemporaryDirectory(prefix="registry-", dir=os.path.dirname(__file__)) as tmp:
            project = Path(tmp)
            package = project / "noemaforge"
            (package / "configs").mkdir(parents=True)
            (package / "src").mkdir(parents=True)
            (package / "configs" / "eval.json").write_text("{}", encoding="utf-8")
            (package / "src" / "model.py").write_text("# model\n", encoding="utf-8")
            registry = {
                "apiVersion": "noemaforge.production-ai/v1",
                "kind": "UnifiedRegistry",
                "entries": [
                    {
                        "kind": "eval-pack",
                        "id": "smoke",
                        "version": "v1",
                        "status": "shadow",
                        "channels": ["stable"],
                        "refs": ["configs/eval.json"],
                    },
                    {
                        "kind": "model",
                        "id": "local",
                        "version": "v1",
                        "status": "shadow",
                        "channels": ["stable"],
                        "refs": ["src/model.py", "src/missing.py"],
                        "eval_pack_refs": ["eval-pack:missing:v1"],
                    },
                ],
            }

            report = urr.validate_unified_registry(
                registry,
                project_root=project,
                package_root=package,
                required_kinds={"model", "eval-pack"},
            )

            self.assertFalse(report["ok"])
            self.assertEqual(1, report["metrics"]["missing_refs"])
            self.assertEqual(1, report["metrics"]["missing_eval_pack_refs"])
            self.assertIn("missing_ref:model:local:v1:src/missing.py", report["failures"])
            self.assertIn("missing_eval_pack_ref:model:local:v1:eval-pack:missing:v1", report["failures"])

    def test_cli_summary_exits_zero_for_workspace_registry(self) -> None:
        registry_path = ROOT / "configs" / "unified-registry.json"
        report = urr.validate_unified_registry(
            json.loads(registry_path.read_text(encoding="utf-8")),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=registry_path,
        )
        self.assertTrue(report["ok"], report["failures"])


if __name__ == "__main__":
    unittest.main()

