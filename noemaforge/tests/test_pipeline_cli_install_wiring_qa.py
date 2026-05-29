#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_cli_install_wiring_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: QA-test registry and documentation coverage for pipeline CLI install wiring.
Inputs: Unified Registry, pipeline CLI install wiring policy and canonical docs.
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

import pipeline_cli_install_wiring_runtime as pciw
import unified_registry_runtime as urr

PACK_ID = "pipeline-cli-install-wiring-core"
CLOSED_ITEM = "[x] Wire pipeline CLI into installed `/usr/local/bin/noemaforge` during installer/apply step."


class PipelineCliInstallWiringQATests(unittest.TestCase):
    def test_pack_is_registered_and_attached_to_firstboot_pipeline(self) -> None:
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
        self.assertIn("configs/pipeline-cli-install-wiring-policy.json", pack["refs"])
        self.assertIn("contracts/pipeline_cli_install_wiring.schema.json", pack["refs"])
        self.assertIn("src/pipeline_cli_install_wiring_runtime.py", pack["refs"])
        self.assertIn("bin/noemaforge", pack["refs"])
        self.assertIn("install_noemaforge_0.32.1_mvp.sh", pack["refs"])
        pipeline = entries.get("pipeline:firstboot-model-selection:0.32.1")
        self.assertIsNotNone(pipeline)
        self.assertIn(f"eval-pack:{PACK_ID}:0.32.1", pipeline["eval_pack_refs"])

    def test_docs_close_installed_pipeline_cli_todo_with_contract_refs(self) -> None:
        report = pciw.validate_pipeline_cli_install_wiring_policy(
            pciw.load_policy(),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
        )
        self.assertTrue(report["ok"], report["failures"])
        backlog = (ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertIn(CLOSED_ITEM, backlog)
        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
            ROOT / "docs" / "wiki" / "pipelines" / "wiki-incremental-patch-pipeline.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn(PACK_ID, text, str(path))
            self.assertIn("/usr/local/bin/noemaforge", text, str(path))
            self.assertIn("pipeline", text.lower(), str(path))

    def test_runtime_stays_offline_and_does_not_run_installer(self) -> None:
        text = (ROOT / "src" / "pipeline_cli_install_wiring_runtime.py").read_text(encoding="utf-8")
        for banned in ["import subprocess", "os.system", "Popen", "socket", "requests", "urllib"]:
            self.assertNotIn(banned, text)
        self.assertIn("no_live_install_execution", (ROOT / "configs" / "pipeline-cli-install-wiring-policy.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

