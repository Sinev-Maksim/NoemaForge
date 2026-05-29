#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_release_provenance_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test release provenance validation on synthetic archive catalogs.
Inputs: Workspace policy expanded with hundreds of signed release provenance examples.
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

import release_provenance_runtime as rpr


class ReleaseProvenancePerformanceTests(unittest.TestCase):
    def test_synthetic_release_provenance_catalog_validates_under_budget(self) -> None:
        policy = rpr.load_policy(ROOT / "configs" / "release-provenance-policy.json")
        base_set = rpr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "release_provenance.example.json")
        base_release = base_set["releases"][0]
        synthetic_set = copy.deepcopy(base_set)
        synthetic_set["releases"] = []
        for index in range(300):
            release = copy.deepcopy(base_release)
            release["id"] = f"noemaforge-release-provenance-{index:03d}"
            release["trace_id"] = f"trace:release:provenance:{index:03d}"
            release["archive"]["path"] = f"dist/noemaforge-{index:03d}.tar.gz"
            release["archive"]["sha256"] = f"{index:064x}"[-64:]
            release["manifest"]["path"] = f"dist/noemaforge-{index:03d}.manifest.json"
            release["manifest"]["sha256"] = f"{index + 300:064x}"[-64:]
            for sig_index, signature in enumerate(release["signatures"]):
                signature["signature_path"] = f"{signature['artifact']}-{index:03d}.sig"
                signature["signature"] = f"base64:synthetic-{index:03d}-{sig_index}"
            synthetic_set["releases"].append(release)

        started = time.perf_counter()
        with patch.object(rpr, "load_example_set", return_value=synthetic_set):
            report = rpr.validate_release_provenance_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["releases"])
        self.assertEqual(300, report["metrics"]["passing_releases"])
        self.assertEqual(600, report["metrics"]["signed_artifacts"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
