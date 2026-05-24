#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_ota_update_layer_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Performance-test OTA Update Layer validation on a synthetic update manifest catalog.
Inputs: Temporary local fixture with hundreds of OTA update manifests.
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
TMP_ROOT = ROOT / "tests" / "_ota"
sys.path.insert(0, str(ROOT / "src"))

import ota_update_layer_runtime as oalr


class OTAUpdateLayerPerformanceTests(unittest.TestCase):
    def tearDown(self) -> None:
        if TMP_ROOT.exists():
            shutil.rmtree(TMP_ROOT)

    def test_synthetic_update_manifest_catalog_validates_under_budget(self) -> None:
        payload = copy.deepcopy(oalr.load_policy(ROOT / "configs" / "ota-update-layer.json"))
        base_manifest = json.loads((PROJECT_ROOT / "prelaunch" / "ota" / "update_manifest.json").read_text(encoding="utf-8"))
        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        payload["update_manifests"] = []
        for index in range(250):
            manifest = copy.deepcopy(base_manifest)
            manifest["id"] = f"ota-update-{index:04d}"
            manifest["candidate_bundle"]["id"] = f"candidate-bundle-{index:04d}"
            manifest["previous_bundle"]["id"] = f"previous-bundle-{index:04d}"
            manifest_ref = TMP_ROOT / f"m{index:04d}.json"
            manifest_ref.write_text(json.dumps(manifest), encoding="utf-8")
            payload["update_manifests"].append({"id": manifest["id"], "ref": f"tests/_ota/m{index:04d}.json"})

        started = time.perf_counter()
        report = oalr.validate_ota_update_layer_policy(payload, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:5])
        self.assertEqual(250, report["metrics"]["update_manifests"])
        self.assertEqual(250, report["metrics"]["passing_update_manifests"])
        self.assertEqual(250, report["metrics"]["staged_rollouts"])
        self.assertEqual(250, report["metrics"]["rollback_enabled"])
        self.assertEqual(250, report["metrics"]["health_gates_passed"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
