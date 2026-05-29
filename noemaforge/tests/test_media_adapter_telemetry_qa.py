#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_media_adapter_telemetry_qa.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: QA-test media adapter telemetry registration, selftests and documentation coverage.
Inputs: Unified Registry, selftest catalog, telemetry policy and canonical documentation.
Outputs: unittest assertions only.
Side effects: Temporary files under unittest temp directories only.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import media_adapter_telemetry_runtime as matr
import selftest_runtime as strt
import unified_registry_runtime as urr


class MediaAdapterTelemetryQATests(unittest.TestCase):
    def test_media_adapter_telemetry_pack_is_registered(self) -> None:
        registry_path = ROOT / "configs" / "unified-registry.json"
        report = urr.validate_unified_registry(
            urr.load_registry(registry_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            registry_path=registry_path,
        )
        self.assertTrue(report["ok"], report["failures"])
        entries = {
            f"{entry['kind']}:{entry['id']}:{entry['version']}": entry
            for entry in report["normalized_registry"]["entries"]
        }
        pack = entries.get("eval-pack:media-adapter-telemetry-core:0.32.1")
        self.assertIsNotNone(pack)
        self.assertIn("configs/media-adapter-telemetry-policy.json", pack["refs"])
        self.assertIn("contracts/media_adapter_telemetry.schema.json", pack["refs"])
        self.assertIn("src/media_adapter_telemetry_runtime.py", pack["refs"])
        self.assertIn("tests/test_media_adapter_telemetry_performance.py", pack["refs"])
        pipeline = entries["pipeline:firstboot-model-selection:0.32.1"]
        self.assertIn("eval-pack:media-adapter-telemetry-core:0.32.1", pipeline["eval_pack_refs"])
        self.assertIn("configs/media-adapter-telemetry-policy.json", pipeline["refs"])

    def test_media_adapter_selftest_suite_runs_without_live_backends(self) -> None:
        catalog = strt.load_catalog(ROOT)
        selected = strt.select_cases(catalog, "media_adapters", None, allow_live=False)
        self.assertEqual(6, len(selected))
        self.assertEqual({"__media_adapter_telemetry__"}, {case["command"][0] for case in selected})
        self.assertTrue(all(case.get("live") is False for case in selected))

        with tempfile.TemporaryDirectory() as raw:
            state = Path(raw) / "state"
            out_dir = Path(raw) / "out"
            stdout = StringIO()
            with contextlib.redirect_stdout(stdout):
                strt.main([
                    "--root",
                    str(ROOT),
                    "--state",
                    str(state),
                    "run",
                    "--suite",
                    "media_adapters",
                    "--out-dir",
                    str(out_dir),
                    "--json",
                ])
            report = json.loads(stdout.getvalue())

        self.assertTrue(report["summary"]["ok"], report["summary"])
        self.assertEqual(6, report["summary"]["case_count"])
        self.assertEqual(6, report["summary"]["passed"])

    def test_docs_and_examples_name_media_adapter_telemetry(self) -> None:
        policy = matr.load_policy(ROOT / "configs" / "media-adapter-telemetry-policy.json")
        report = matr.validate_media_adapter_telemetry_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        self.assertTrue(report["ok"], report["failures"])

        for path in [
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "TODO.md",
            ROOT / "docs" / "backlog" / "ROADMAP_AND_TODO.md",
            ROOT / "docs" / "reference" / "PROJECT_CONTEXT.md",
            ROOT / "docs" / "history" / "CHANGELOG.md",
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("media-adapter-telemetry-core", text)
            self.assertIn("telemetry", text.lower())
            self.assertIn("selftest", text.lower())


if __name__ == "__main__":
    unittest.main()

