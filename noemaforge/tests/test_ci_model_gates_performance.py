#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_ci_model_gates_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Performance-test offline CI model gate validation on a synthetic multi-gate policy.
Inputs: Temporary local fixture with hundreds of CI model gates.
Outputs: unittest assertions only.
Side effects: Creates and removes a temporary fixture directory.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import os
import shutil
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
TMP_ROOT = ROOT / "tests" / "_tmp_ci_model_gates_perf"
sys.path.insert(0, str(ROOT / "src"))

import ci_model_gates_runtime as cmgr


class CIModelGatesPerformanceTests(unittest.TestCase):
    def tearDown(self) -> None:
        if TMP_ROOT.exists():
            shutil.rmtree(TMP_ROOT)

    def test_synthetic_gate_policy_validates_under_budget(self) -> None:
        payload = copy.deepcopy(cmgr.load_policy(ROOT / "configs" / "ci-model-gates.json"))
        project = TMP_ROOT / "project"
        package = project / "noemaforge"
        ref_path = project / "noemaforge" / "configs" / "ci-model-gates.json"
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        ref_path.write_text("{}", encoding="utf-8")
        evidence_path = project / "prelaunch" / "evidence" / "ci-model-gates" / "release_evidence.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text("{}", encoding="utf-8")

        payload["refs"] = ["noemaforge/configs/ci-model-gates.json"]
        base_gate = copy.deepcopy(payload["gates"][0])
        base_gate["refs"] = ["noemaforge/configs/ci-model-gates.json"]
        base_gate["release_evidence_ref"] = "prelaunch/evidence/ci-model-gates/release_evidence.json"
        payload["gates"] = []
        for index in range(500):
            gate = copy.deepcopy(base_gate)
            gate["id"] = f"edge-model-ci-gate-{index:04d}"
            payload["gates"].append(gate)

        started = time.perf_counter()
        report = cmgr.validate_ci_model_gates(payload, project_root=project, package_root=package)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:5])
        self.assertEqual(500, report["metrics"]["gates"])
        self.assertEqual(500, report["metrics"]["passing_gates"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
