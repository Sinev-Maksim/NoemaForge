#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_git_exchange_quarantine_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test git_exchange validation on synthetic import catalogs.
Inputs: Workspace policy expanded with hundreds of GitExchangeImport records.
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

import git_exchange_quarantine_runtime as geqr


class GitExchangeQuarantinePerformanceTests(unittest.TestCase):
    def test_synthetic_git_exchange_catalog_validates_under_budget(self) -> None:
        policy = geqr.load_policy(ROOT / "configs" / "git-exchange-quarantine-policy.json")
        base_set = geqr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "git_exchange_quarantine.example.json")
        synthetic_set = copy.deepcopy(base_set)
        base_imports = copy.deepcopy(base_set["imports"])
        synthetic_set["imports"] = []
        for index in range(300):
            item = copy.deepcopy(base_imports[index % len(base_imports)])
            item["id"] = f"{item['id']}-{index:03d}"
            item["trace_id"] = f"{item['trace_id']}:{index:03d}"
            item["pack_id"] = f"{item['pack_id']}.{index:03d}"
            item["manifest_sha256"] = f"{index + 1:064x}"[-64:]
            synthetic_set["imports"].append(item)

        started = time.perf_counter()
        with patch.object(geqr, "load_example_set", return_value=synthetic_set):
            report = geqr.validate_git_exchange_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["imports"])
        self.assertEqual(300, report["metrics"]["passing_imports"])
        self.assertEqual(6, report["metrics"]["pack_kinds"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
