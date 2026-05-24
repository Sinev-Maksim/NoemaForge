#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_cpu_gpu_scorecard_separation_runtime.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate separate CPU/GPU scorecard path contracts.
Inputs: Workspace CPU/GPU scorecard separation policy and scorecard writer sources.
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

import cpu_gpu_scorecard_separation_runtime as cgs
import model_scorecards
import production_ai_contracts as pac


class CpuGpuScorecardSeparationRuntimeTests(unittest.TestCase):
    def test_workspace_scorecard_separation_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "cpu-gpu-scorecard-separation-policy.json"
        validation = cgs.validate_cpu_gpu_scorecard_separation_policy(
            cgs.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(validation["ok"], validation["failures"])
        self.assertEqual(2, validation["metrics"]["examples"])
        self.assertEqual(2, validation["metrics"]["passing_examples"])

        gate = pac.evaluate_gate(
            {"change_id": "cpu-gpu-scorecard-separation-core", "domain": "pipeline"},
            cgs.cpu_gpu_scorecard_separation_report_to_gate_evidence(validation, artifact_uri="reports/cpu-gpu-scorecard-separation.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_model_scorecard_path_uses_runtime_device_namespaces(self) -> None:
        root = "/var/lib/noemaforge/model_scorecards"
        cpu_path = model_scorecards._scorecard_path("qwen2.5-3b", "operator.admin", "administrator", "llm", root=root, runtime_device="cpu")
        gpu_path = model_scorecards._scorecard_path("qwen2.5-14b", "research.deep", "researcher", "llm", root=root, runtime_device="cuda")
        legacy_path = model_scorecards._scorecard_path("qwen2.5-3b", "operator.admin", "administrator", "llm", root=root)

        self.assertTrue(cpu_path.replace("\\", "/").endswith("model_scorecards/cpu/qwen2.5-3b/operator.admin__administrator__llm.json"))
        self.assertTrue(gpu_path.replace("\\", "/").endswith("model_scorecards/gpu/qwen2.5-14b/research.deep__researcher__llm.json"))
        self.assertTrue(legacy_path.replace("\\", "/").endswith("model_scorecards/qwen2.5-3b/operator.admin__administrator__llm.json"))
        self.assertEqual("gpu", model_scorecards.normalize_scorecard_device("cuda"))

    def test_role_tournament_writer_declares_device_field_and_env_switch(self) -> None:
        source = (ROOT / "src" / "role_tournament.py").read_text(encoding="utf-8")
        self.assertIn("NOEMAFORGE_SCORECARD_DEVICE", source)
        self.assertIn("runtime_device", source)
        self.assertIn("SCORECARD_DEVICE_ALIASES", source)
        self.assertIn("device_root", source)


if __name__ == "__main__":
    unittest.main()
