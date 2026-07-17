"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_autonomous_pipeline_windows_collect_guard.py
Zone: tests/ci
Version: 0.33.0
Created: 2026-07-14
Purpose: Lock the Windows collect-only guard for ToolProxy/Discord imports.
Inputs: .github/workflows/autonomous-pipeline.yml.
Outputs: Pass/fail assertions.
Tests: python -m unittest noemaforge.tests.test_autonomous_pipeline_windows_collect_guard
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import unittest
from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "autonomous-pipeline.yml"


class AutonomousPipelineWindowsCollectGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        cls.workflow_text = WORKFLOW.read_text(encoding="utf-8")
        cls.codex_job = cls.workflow["jobs"]["codex-review"]

    def test_codex_review_still_runs_on_self_hosted_windows(self) -> None:
        self.assertEqual(["self-hosted", "Windows", "codex"], self.codex_job["runs-on"])

    def test_windows_toolproxy_collect_guard_is_present(self) -> None:
        steps = {
            step.get("name"): step
            for step in self.codex_job["steps"]
            if isinstance(step, dict) and step.get("name")
        }
        step = steps.get("Windows collect-only guard for ToolProxy imports")
        self.assertIsNotNone(step)
        self.assertEqual("pwsh", step["shell"])
        self.assertEqual("steps.gate.outputs.paused != 'true'", step["if"])

        run = step["run"]
        self.assertIn('python -c "import pytest"', run)
        self.assertIn("if ($LASTEXITCODE -ne 0)", run)
        self.assertIn("pytest is not available in the Codex runner Python environment", run)
        self.assertIn("exit 1", run)
        self.assertNotIn("python -m pip install", run)
        self.assertIn("python -m pytest --collect-only -q", run)
        self.assertIn("noemaforge/tests/test_toolproxy_voice_chat.py", run)
        self.assertIn("noemaforge/tests/test_toolproxy_roundtrip_and_local_workflows.py", run)
        self.assertIn("noemaforge/tests/test_discord_bridge.py", run)
        self.assertIn("PYTHONPATH", run)

    def test_codex_exec_help_probe_and_artifacts_are_plumbed(self) -> None:
        steps = self.codex_job["steps"]
        run_step = next(step for step in steps if step.get("name") == "Run Codex CLI review")
        run = run_step["run"]

        self.assertIn("exec --help", run)
        self.assertIn("codex_exec_help.txt", run)
        self.assertIn("codex_exec_capabilities.json", run)
        self.assertIn("help_exit_code", run)
        self.assertIn("sandbox_flag", run)
        self.assertIn("approval_mode_flag", run)
        self.assertIn("Test-CodexExecOption", run)
        self.assertIn("--approval-mode", run)
        self.assertIn("--sandbox", run)
        self.assertIn("-s", run)
        self.assertIn("never", run)
        self.assertIn("read-only", run)

    def test_regression_guard_is_documented_in_todo(self) -> None:
        todo = (REPO / "noemaforge" / "docs" / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("Windows collection regression guard", todo)
        self.assertIn("autonomous-pipeline.yml", todo)


if __name__ == "__main__":
    unittest.main()
