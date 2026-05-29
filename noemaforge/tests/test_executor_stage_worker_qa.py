#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_executor_stage_worker_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test executor-stage-worker discoverability through registry and docs.
Inputs: Unified Registry, executor-stage-worker policy and canonical documentation files.
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

import executor_stage_worker_runtime as eswr
import unified_registry_runtime as urr

CLOSURE = "Closed by `executor-stage-worker-core`"


class ExecutorStageWorkerQATests(unittest.TestCase):
    def test_executor_stage_worker_pack_is_registered_and_attached_to_pipeline(self) -> None:
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
        pack = entries.get("eval-pack:executor-stage-worker-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/executor-stage-worker-policy.json", pack["refs"])
        self.assertIn("contracts/executor_stage_worker.schema.json", pack["refs"])
        self.assertIn("src/pipeline_runtime.py", pack["refs"])
        self.assertIn("src/executor_stage_worker_runtime.py", pack["refs"])
        self.assertIn("tests/test_executor_stage_worker_performance.py", pack["refs"])
        self.assertIn("docs/TODO.md", pack["refs"])
        self.assertIn("docs/reference/PROJECT_CONTEXT.md", pack["refs"])

        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:executor-stage-worker-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/executor-stage-worker-policy.json", pipeline["refs"])
        self.assertIn("src/executor_stage_worker_runtime.py", pipeline["refs"])

    def test_executor_stage_worker_docs_policy_and_changelog_are_discoverable(self) -> None:
        policy = eswr.load_policy(ROOT / "configs" / "executor-stage-worker-policy.json")
        self.assertEqual("ExecutorStageWorkerPolicy", policy["kind"])
        self.assertEqual("contract_driven_executor_step", policy["policy"]["activation_state"])
        self.assertIn("executor-step", policy["policy"]["required_pipeline_commands"])

        validation = eswr.validate_executor_stage_worker_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(validation["ok"], validation["failures"])

        for path in [
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "TODO.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("[x] Promote stage executor from scaffold to real execution engine.", text)
            self.assertIn("executor-stage-worker-core", text)
            self.assertIn(CLOSURE, text)

        context = (ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn("stage executor has moved from scaffold to a contract-driven local worker", context)
        self.assertIn("executor-stage-worker-core", context)
        self.assertIn(CLOSURE, context)

        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("executor-stage-worker-core", text)
            self.assertIn("noemaforge pipeline executor-step", text)
            self.assertIn(CLOSURE, text)

    def test_executor_stage_worker_refs_use_canonical_docs_paths(self) -> None:
        policy = eswr.load_policy(ROOT / "configs" / "executor-stage-worker-policy.json")
        refs = set(policy["refs"])

        self.assertIn("docs/TODO.md", refs)
        self.assertIn("docs/reference/PROJECT_CONTEXT.md", refs)
        self.assertIn("noemaforge/docs/TODO.md", refs)
        self.assertFalse({"README.md", "TODO.md", "noemaforge/TODO.md"} & refs)
        docs_refs = {ref for ref in refs if ref.endswith(".md")}
        self.assertTrue(all(ref.startswith(("docs/", "noemaforge/docs/")) for ref in docs_refs))


if __name__ == "__main__":
    unittest.main()

