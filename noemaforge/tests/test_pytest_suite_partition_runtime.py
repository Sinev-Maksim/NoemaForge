#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pytest_suite_partition_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Validate bounded pytest suite partitioning for pipeline-runtime hang investigation.
Inputs: Synthetic test file lists and pytest suite partition policy.
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

import production_ai_contracts as pac
import pytest_suite_partition_runtime as pspr


class PytestSuitePartitionRuntimeTests(unittest.TestCase):
    def test_policy_validates_and_maps_to_pipeline_gate_evidence(self) -> None:
        policy = pspr.load_policy(ROOT / "configs" / "pytest-suite-partition-policy.json")
        report = pspr.validate_pytest_suite_partition_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)

        self.assertTrue(report["ok"], report["failures"])
        gate = pac.evaluate_gate(
            {
                "change_id": "pytest-suite-partition-core",
                "domain": "pipeline",
                "required_checks": ["pipeline_eval", "rollback_plan"],
            },
            {
                "artifact_uri": "reports/pytest-suite-partition.json",
                "run_at": "2026-05-20T00:00:00Z",
                "checks": [
                    {"id": "pipeline_eval", "status": "passed" if report["ok"] else "failed"},
                    {"id": "rollback_plan", "status": "passed"},
                ],
            },
        )
        self.assertTrue(gate["ok"], gate)

    def test_monolithic_pytest_command_is_blocked(self) -> None:
        policy = pspr.load_policy(ROOT / "configs" / "pytest-suite-partition-policy.json")
        report = pspr.validate_pytest_command("pytest noemaforge/tests", policy=policy)

        self.assertFalse(report["ok"])
        self.assertIn("forbidden_monolithic_pytest_command", report["failures"])
        self.assertIn("pytest_command_missing_timeout", report["failures"])

    def test_partition_plan_isolates_pipeline_runtime_tests(self) -> None:
        policy = pspr.load_policy(ROOT / "configs" / "pytest-suite-partition-policy.json")
        tests = [
            "noemaforge/tests/test_pipeline_runtime_03009.py",
            "noemaforge/tests/test_pipeline_template_append_runtime.py",
            "noemaforge/tests/test_docs_hygiene_runtime.py",
            "noemaforge/tests/test_unified_registry_runtime.py",
        ]
        plan = pspr.partition_tests(tests, policy=policy)
        validation = pspr.validate_partition_plan(plan, policy=policy)

        self.assertTrue(validation["ok"], validation["failures"])
        labels = {shard["label"] for shard in plan["shards"]}
        self.assertEqual({"general", "pipeline_runtime"}, labels)
        pipeline_shards = [shard for shard in plan["shards"] if shard["label"] == "pipeline_runtime"]
        self.assertTrue(pipeline_shards)
        for shard in pipeline_shards:
            self.assertTrue(all("pipeline" in Path(path).name for path in shard["tests"]))
            self.assertLessEqual(shard["timeout_seconds"], policy["policy"]["required_timeout_seconds"])

    def test_discovery_finds_active_tests_without_executing_them(self) -> None:
        policy = pspr.load_policy(ROOT / "configs" / "pytest-suite-partition-policy.json")
        files = pspr.discover_test_files(ROOT / "tests")
        plan = pspr.partition_tests(files, policy=policy)
        validation = pspr.validate_partition_plan(plan, policy=policy)

        self.assertIn((ROOT / "tests" / "test_pipeline_runtime_03009.py").as_posix(), files)
        self.assertTrue(validation["ok"], validation["failures"])
        self.assertGreater(plan["metrics"]["pipeline_runtime_shards"], 0)


if __name__ == "__main__":
    unittest.main()
