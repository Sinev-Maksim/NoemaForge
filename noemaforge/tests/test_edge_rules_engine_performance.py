#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_edge_rules_engine_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Performance-test Edge Rules Engine validation on a synthetic rule catalog.
Inputs: Temporary local fixture with hundreds of edge rules.
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
TMP_ROOT = ROOT / "tests" / "_ter"
sys.path.insert(0, str(ROOT / "src"))

import edge_rules_engine_runtime as erer


class EdgeRulesEnginePerformanceTests(unittest.TestCase):
    def tearDown(self) -> None:
        if TMP_ROOT.exists():
            shutil.rmtree(TMP_ROOT)

    def test_synthetic_rule_catalog_validates_under_budget(self) -> None:
        payload = copy.deepcopy(erer.load_policy(ROOT / "configs" / "edge-rules-engine-policy.json"))
        project = TMP_ROOT / "p"
        package = project / "noemaforge"
        policy_ref = package / "configs" / "p.json"
        manifest_ref = project / "m.json"
        rules_ref = project / "r.json"
        policy_ref.parent.mkdir(parents=True, exist_ok=True)
        policy_ref.write_text("{}", encoding="utf-8")
        manifest_ref.write_text("{}", encoding="utf-8")
        rules_ref.write_text("{}", encoding="utf-8")

        payload["refs"] = ["noemaforge/configs/p.json", "m.json", "r.json"]
        base_rule = copy.deepcopy(payload["rules"][1])
        base_rule["signed_model_manifest_ref"] = "m.json"
        base_rule["refs"] = ["m.json", "r.json"]
        payload["rules"] = []
        payload["rules"].append(copy.deepcopy(payload["rules"]) if False else copy.deepcopy(base_rule))
        payload["rules"][0]["id"] = "whitebox-only-synthetic"
        payload["rules"][0]["mode"] = "whitebox_only"
        payload["rules"][0]["stage"] = "pre_ml"
        payload["rules"][0]["model_score_may_apply"] = False
        payload["rules"][0]["applies_after_ml"] = False
        for index in range(600):
            rule = copy.deepcopy(base_rule)
            rule["id"] = f"guarded-ml-rule-{index:04d}"
            payload["rules"].append(rule)

        started = time.perf_counter()
        report = erer.validate_edge_rules_engine_policy(payload, project_root=project, package_root=package)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:5])
        self.assertEqual(601, report["metrics"]["rules"])
        self.assertEqual(600, report["metrics"]["guarded_ml_rules"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
