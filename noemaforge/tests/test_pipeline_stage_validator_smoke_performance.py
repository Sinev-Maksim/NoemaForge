#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_stage_validator_smoke_performance.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-21
Modified: 2026-05-21
Purpose: Bound regression cost for offline pipeline stage validation.
Inputs: Small deterministic run fixture.
Outputs: unittest assertions only.
Side effects: Creates temporary directories only.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import contextlib
import gc
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

import pipeline_runtime as pr


def call_pipeline(argv: list[str]) -> tuple[int, dict]:
    stdout = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(stdout):
        try:
            pr.main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    gc.collect()
    raw = stdout.getvalue().strip()
    return code, json.loads(raw) if raw else {}


class PipelineStageValidatorSmokePerformanceTests(unittest.TestCase):
    def test_stage_validation_stays_bounded_for_small_ci_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            state = tmp / "state"
            code, created = call_pipeline([
                "run",
                "public_mwp",
                "--task-id",
                "stage_validator_perf",
                "--run-id",
                "run_stage_validator_perf",
                "--request",
                "stage validator performance fixture",
                "--state",
                str(state),
                "--root",
                str(ROOT),
            ])
            self.assertEqual(0, code)
            conn = pr.db_connect(state)
            run = pr.get_run(conn, created["run_id"])
            artifacts = pr._artifact_rows(conn, created["run_id"])
            stages = list(((run.get("manifest") or {}).get("pipeline") or {}).get("stages") or [])
            started = time.perf_counter()
            report_count = 0
            for _ in range(120):
                for stage in stages:
                    pr.validate_stage_artifacts(run, artifacts, stage)
                    report_count += 1
            elapsed = time.perf_counter() - started
            conn.close()
        self.assertGreater(report_count, 0)
        self.assertLess(elapsed, 2.0, f"stage validation took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
