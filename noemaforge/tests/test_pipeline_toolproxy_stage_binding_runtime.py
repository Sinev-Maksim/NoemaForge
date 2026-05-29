#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_toolproxy_stage_binding_runtime.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Unit-test pipeline ToolProxy stage-binding runtime behavior.
Inputs: Pipeline runtime helpers and ToolProxy stage-binding policy.
Outputs: unittest assertions only.
Side effects: Creates temporary directories only.
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

import pipeline_runtime as pr
import pipeline_toolproxy_stage_binding_runtime as ptsb


class PipelineToolProxyStageBindingRuntimeTests(unittest.TestCase):
    def test_policy_validates_pipeline_runtime_contract(self) -> None:
        report = ptsb.validate_pipeline_toolproxy_stage_binding_policy(
            ptsb.load_policy(),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
        )
        self.assertTrue(report["ok"], report["failures"])
        summary = report["summary"]
        self.assertTrue(summary["capability_token_required"])
        self.assertTrue(summary["network_default_deny"])
        self.assertTrue(summary["exec_sandbox_guard"])
        self.assertTrue(summary["public_readmostly_guard"])

    def test_evolution_development_allows_write_and_worktree_with_approval(self) -> None:
        binding = pr.build_toolproxy_stage_binding("evolution", "development", "ask_before_write")
        self.assertTrue(binding["capability_token_required"])
        self.assertTrue(binding["approval_required"])
        self.assertFalse(binding["network_allowed"])
        self.assertIn("fs.write", binding["allowed_actions"])
        self.assertIn("worktree.enter", binding["allowed_actions"])
        self.assertIn("db.write", binding["blocked_actions"])
        self.assertIn("contracts/capability_token.schema.json", binding["capability_schema_ref"])

    def test_testing_stage_requires_sandbox_for_exec(self) -> None:
        binding = pr.build_toolproxy_stage_binding("evolution", "unit_testing", "ask_before_write")
        self.assertIn("exec.run", binding["allowed_actions"])
        self.assertIn("exec.run", binding["sandboxed_actions"])
        self.assertTrue(binding["sandbox_required"])

    def test_public_mwp_readmostly_does_not_gain_write_or_exec(self) -> None:
        binding = pr.build_toolproxy_stage_binding("public_mwp", "status_check", "guided_readmostly")
        self.assertFalse(binding["approval_required"])
        self.assertNotIn("fs.write", binding["allowed_actions"])
        self.assertNotIn("exec.run", binding["allowed_actions"])
        self.assertNotIn("worktree.enter", binding["allowed_actions"])

    def test_run_files_include_manifest_and_context_packet_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "runs" / "run-binding"
            pipeline = dict(pr.DEFAULT_PIPELINES["evolution"])
            pipeline["id"] = "evolution"
            packet_paths, _ = pr.write_run_files(ROOT, run_dir, pipeline, pr.DEFAULT_TEAMS["development_evolution_team"], "task", "project", "request")
            binding_path = run_dir / "toolproxy_stage_bindings.json"
            self.assertTrue(binding_path.exists())
            bindings = json.loads(binding_path.read_text(encoding="utf-8"))
            self.assertIn("development", bindings)
            sidecar = Path(packet_paths[0]).with_suffix(".json")
            packet = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertIn("toolproxy_stage_binding", packet)
            self.assertEqual("pipeline:evolution:stage:intake", packet["toolproxy_stage_binding"]["scope"])


if __name__ == "__main__":
    unittest.main()
