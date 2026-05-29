#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_tinyml_node_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Performance-test TinyML Node validation on a synthetic MCU node catalog.
Inputs: Temporary local fixture with hundreds of TinyML nodes.
Outputs: unittest assertions only.
Side effects: Creates and removes a temporary fixture directory.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
TMP_ROOT = ROOT / "tests" / "_ttn"
sys.path.insert(0, str(ROOT / "src"))

import tinyml_node_runtime as tnr


class TinyMLNodePerformanceTests(unittest.TestCase):
    def tearDown(self) -> None:
        if TMP_ROOT.exists():
            shutil.rmtree(TMP_ROOT)

    def test_synthetic_node_catalog_validates_under_budget(self) -> None:
        payload = copy.deepcopy(tnr.load_policy(ROOT / "configs" / "tinyml-node-policy.json"))
        project = TMP_ROOT / "p"
        package = project / "noemaforge"
        policy_ref = package / "configs" / "p.json"
        golden_ref = project / "g.jsonl"
        arena_ref = project / "a.json"
        manifest_ref = project / "m.json"
        rules_ref = project / "r.json"
        policy_ref.parent.mkdir(parents=True, exist_ok=True)
        policy_ref.write_text("{}", encoding="utf-8")
        manifest_ref.write_text("{}", encoding="utf-8")
        rules_ref.write_text("{}", encoding="utf-8")
        golden_ref.write_text(
            "\n".join(
                json.dumps({"case_id": f"case-{index}", "input": [index], "expected_output": {"score": index}})
                for index in range(3)
            ),
            encoding="utf-8",
        )
        arena_ref.write_text(
            json.dumps({"kind": "StaticArenaReport", "arena_bytes": 32768, "peak_bytes": 24576}),
            encoding="utf-8",
        )

        payload["refs"] = ["noemaforge/configs/p.json", "g.jsonl", "a.json", "m.json", "r.json"]
        base_node = copy.deepcopy(payload["nodes"][0])
        base_node["signed_model_manifest_ref"] = "m.json"
        base_node["edge_rules_ref"] = "r.json"
        base_node["golden_vectors_ref"] = "g.jsonl"
        base_node["static_arena_report_ref"] = "a.json"
        base_node["refs"] = ["g.jsonl", "a.json", "m.json", "r.json"]
        payload["nodes"] = []
        for index in range(500):
            node = copy.deepcopy(base_node)
            node["id"] = f"tinyml-node-{index:04d}"
            payload["nodes"].append(node)

        started = time.perf_counter()
        report = tnr.validate_tinyml_node_policy(payload, project_root=project, package_root=package)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:5])
        self.assertEqual(500, report["metrics"]["nodes"])
        self.assertEqual(500, report["metrics"]["passing_nodes"])
        self.assertEqual(0, report["metrics"]["direct_control_decision_nodes"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
