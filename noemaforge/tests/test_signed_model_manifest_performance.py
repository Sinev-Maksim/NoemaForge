#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_signed_model_manifest_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Performance-test signed model manifest validation on a synthetic manifest catalog.
Inputs: Temporary local fixture with hundreds of signed manifests.
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
PROJECT_ROOT = ROOT.parent
TMP_ROOT = ROOT / "tests" / "_tsmm"
sys.path.insert(0, str(ROOT / "src"))

import signed_model_manifest_runtime as smmr


class SignedModelManifestPerformanceTests(unittest.TestCase):
    def tearDown(self) -> None:
        if TMP_ROOT.exists():
            shutil.rmtree(TMP_ROOT)

    def test_synthetic_manifest_catalog_validates_under_budget(self) -> None:
        source_policy = smmr.load_policy(ROOT / "configs" / "signed-model-manifest-policy.json")
        source_manifest = smmr.load_manifest(PROJECT_ROOT / "prelaunch" / "manifests" / "models" / "example_edge_model.manifest.json")
        payload = copy.deepcopy(source_policy)
        project = TMP_ROOT / "p"
        package = project / "noemaforge"
        policy_ref = package / "configs" / "p.json"
        review_dir = project / "e"
        review_ref = review_dir / "r.json"
        manifests_dir = project / "m"
        policy_ref.parent.mkdir(parents=True, exist_ok=True)
        review_dir.mkdir(parents=True, exist_ok=True)
        manifests_dir.mkdir(parents=True, exist_ok=True)
        policy_ref.write_text("{}", encoding="utf-8")
        review_ref.write_text("{}", encoding="utf-8")

        payload["refs"] = ["noemaforge/configs/p.json"]
        payload["manifest_refs"] = []
        for index in range(350):
            manifest = copy.deepcopy(source_manifest)
            manifest["id"] = f"example-edge-model-{index:04d}"
            manifest["model_id"] = f"example_edge_model_{index:04d}"
            manifest["qa_gate"]["review_ref"] = "e/r.json"
            manifest["refs"] = [
                "noemaforge/configs/p.json",
                "e/r.json",
            ]
            ref = f"m/m{index:04d}.json"
            (project / ref).write_text(json.dumps(manifest), encoding="utf-8")
            payload["manifest_refs"].append({"id": manifest["id"], "ref": ref})

        started = time.perf_counter()
        report = smmr.validate_signed_model_manifest_policy(payload, project_root=project, package_root=package)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:5])
        self.assertEqual(350, report["metrics"]["manifests"])
        self.assertEqual(350, report["metrics"]["passing_manifests"])
        self.assertEqual(350, report["metrics"]["signed_manifests"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
