#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_stage_validator_smoke_qa.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Verify registry and documentation integration for pipeline stage validator smoke.
Inputs: Unified registry plus canonical documentation files.
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

PACK_ID = "pipeline-stage-validator-smoke-core"
CLOSURE = "Closed by `pipeline-stage-validator-smoke-core`"


class PipelineStageValidatorSmokeQATests(unittest.TestCase):
    def test_registry_contains_eval_pack_and_pipeline_links(self) -> None:
        registry = json.loads((ROOT / "configs" / "unified-registry.json").read_text(encoding="utf-8"))
        entries = {f"{entry['kind']}:{entry['id']}:{entry['version']}": entry for entry in registry["entries"]}
        pack_ref = "eval-pack:pipeline-stage-validator-smoke-core:0.32.0"
        self.assertIn(pack_ref, entries)
        pack = entries[pack_ref]
        self.assertIn("configs/pipeline-stage-validator-smoke-policy.json", pack["refs"])
        self.assertIn("contracts/pipeline_stage_validator_smoke.schema.json", pack["refs"])
        self.assertIn("src/pipeline_stage_validator_smoke_runtime.py", pack["refs"])
        self.assertIn("tests/test_pipeline_stage_validator_smoke_performance.py", pack["refs"])
        pipeline = entries["pipeline:firstboot-model-selection:0.31.13.alpha-patched1"]
        self.assertIn(pack_ref, pipeline["eval_pack_refs"])
        self.assertIn("src/pipeline_stage_validator_smoke_runtime.py", pipeline["refs"])

    def test_policy_schema_and_example_are_present(self) -> None:
        policy = json.loads((ROOT / "configs" / "pipeline-stage-validator-smoke-policy.json").read_text(encoding="utf-8"))
        schema = json.loads((ROOT / "contracts" / "pipeline_stage_validator_smoke.schema.json").read_text(encoding="utf-8"))
        examples = json.loads((PROJECT_ROOT / "prelaunch" / "governance" / "pipeline_stage_validator_smoke.example.json").read_text(encoding="utf-8"))
        self.assertEqual(PACK_ID, policy["id"])
        self.assertEqual("noemaforge.pipeline-stage-validator-smoke/v1", policy["apiVersion"])
        self.assertEqual(True, schema["properties"]["offline_only"]["const"])
        self.assertGreaterEqual(len(examples["examples"]), 2)

    def test_canonical_docs_and_changelog_close_selected_item(self) -> None:
        docs = [
            PROJECT_ROOT / "noemaforge" / "docs" / "README.md",
            PROJECT_ROOT / "noemaforge" / "docs" / "TODO.md",
            PROJECT_ROOT / "noemaforge" / "docs" / "reference" / "PROJECT_CONTEXT.md",
            PROJECT_ROOT / "noemaforge" / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            PROJECT_ROOT / "noemaforge" / "docs" / "wiki" / "pipelines" / "wiki-incremental-patch-pipeline.md",
            PROJECT_ROOT / "noemaforge" / "docs" / "history" / "CHANGELOG.md",
        ]
        for path in docs:
            text = path.read_text(encoding="utf-8")
            self.assertIn(PACK_ID, text, path)
        todo_text = (PROJECT_ROOT / "noemaforge" / "docs" / "TODO.md").read_text(encoding="utf-8")
        roadmap_text = (PROJECT_ROOT / "noemaforge" / "docs" / "backlog" / "ROADMAP_AND_TODO.md").read_text(encoding="utf-8")
        self.assertIn(CLOSURE, todo_text)
        self.assertIn("- [x] Add stage validators and smoke tests.", roadmap_text)


if __name__ == "__main__":
    unittest.main()

