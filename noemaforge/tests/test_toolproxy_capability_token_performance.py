#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_toolproxy_capability_token_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test ToolProxy capability-token validation on synthetic flow catalogs.
Inputs: Workspace policy expanded with hundreds of offline token UX flows.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import toolproxy_capability_token_runtime as tctr


class ToolProxyCapabilityTokenPerformanceTests(unittest.TestCase):
    def test_toolproxy_capability_docs_refs_stay_canonical_and_bounded(self) -> None:
        policy = tctr.load_policy(ROOT / "configs" / "toolproxy-capability-token-policy.json")
        refs = policy["refs"]
        legacy_refs = {"README.md", "TODO.md", "noemaforge/TODO.md"}

        started = time.perf_counter()
        for _ in range(2500):
            docs_refs = [ref for ref in refs if ref.endswith(".md")]
            canonical = all(ref.startswith(("docs/", "noemaforge/docs/")) for ref in docs_refs)
            legacy_free = legacy_refs.isdisjoint(refs)
            bounded = len(docs_refs) <= 10
        elapsed = time.perf_counter() - started

        self.assertTrue(canonical)
        self.assertTrue(legacy_free)
        self.assertTrue(bounded)
        self.assertLess(elapsed, 0.5)

    def test_synthetic_token_flow_catalog_validates_under_budget(self) -> None:
        policy = tctr.load_policy(ROOT / "configs" / "toolproxy-capability-token-policy.json")
        base_set = tctr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "toolproxy_capability_token.example.json")
        base_flow = base_set["flows"][0]
        synthetic_set = copy.deepcopy(base_set)
        synthetic_set["flows"] = []
        for index in range(300):
            flow = copy.deepcopy(base_flow)
            flow["id"] = f"offline-issue-list-verify-revoke-smoke-{index:03d}"
            flow["trace_id"] = f"trace:toolproxy:capability-token-smoke:{index:03d}"
            flow["issue"]["token_output"] = f"tok-example-{index:03d}.***"
            flow["issue"]["issued_to"]["run_id"] = f"smoke-{index:03d}"
            flow["record"]["token_id"] = f"tok-example-{index:03d}"
            flow["record"]["trace_id"] = flow["trace_id"]
            flow["record"]["issued_to"]["run_id"] = f"smoke-{index:03d}"
            flow["record"]["secret_sha256"] = f"{index:064x}"[-64:]
            synthetic_set["flows"].append(flow)

        started = time.perf_counter()
        with patch.object(tctr, "load_example_set", return_value=synthetic_set):
            report = tctr.validate_toolproxy_capability_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["flows"])
        self.assertEqual(300, report["metrics"]["passing_flows"])
        self.assertEqual(5, report["metrics"]["required_ux_commands"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
