#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_template_append_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test reviewed pipeline template append validation.
Inputs: Workspace template-append policy and synthetic workflow templates.
Outputs: unittest assertions only.
Side effects: Temporary files under unittest temp directories only.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import pipeline_runtime as prt


def call_pipeline(argv: list[str]) -> tuple[int, dict]:
    stdout = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(stdout):
        try:
            prt.main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, json.loads(stdout.getvalue())


@unittest.skipIf(sys.platform == "win32", "wall-time threshold tuned for Linux/BigBro-BOS")
class PipelineTemplateAppendPerformanceTests(unittest.TestCase):
    def test_synthetic_template_append_batch_stays_lightweight(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source = tmp / "source.json"
            source.write_text(json.dumps({"nodes": [{"name": "Webhook"}, {"name": "Normalize"}], "connections": {}}), encoding="utf-8")
            start = time.perf_counter()
            for index in range(80):
                draft = tmp / f"draft-{index}.json"
                out = tmp / f"pipelines-{index}.local.json"
                import_code, _ = call_pipeline([
                    "template-import",
                    str(source),
                    "--pipeline-id",
                    f"perf_import_{index}",
                    "--out",
                    str(draft),
                    "--root",
                    str(ROOT),
                ])
                append_code, appended = call_pipeline([
                    "template-append",
                    str(draft),
                    "--approve",
                    "--approved-by",
                    "perf-operator",
                    "--out",
                    str(out),
                    "--root",
                    str(ROOT),
                ])
            elapsed = time.perf_counter() - start

        self.assertEqual(0, import_code)
        self.assertEqual(0, append_code)
        self.assertTrue(appended["ok"])
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
