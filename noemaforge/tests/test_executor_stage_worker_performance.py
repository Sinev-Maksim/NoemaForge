#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_executor_stage_worker_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test contract-driven executor-step stage worker checks.
Inputs: Synthetic pipeline runs only.
Outputs: unittest assertions only.
Side effects: Temporary files under unittest temp directories only.
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
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import pipeline_runtime as prt

PARSER = prt.build_parser()
PIPELINE_CATALOG = prt.load_pipeline_catalog(ROOT)
TEAM_CATALOG = prt.load_team_catalog(ROOT)


def call_pipeline(argv: list[str]) -> tuple[int, dict]:
    stdout = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(stdout):
        try:
            args = PARSER.parse_args(prt.normalize_global_argv(argv))
            args.func(args)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, json.loads(stdout.getvalue())


class ExecutorStageWorkerPerformanceTests(unittest.TestCase):
    def test_executor_stage_worker_docs_refs_stay_canonical_and_bounded(self) -> None:
        policy = json.loads((ROOT / "configs" / "executor-stage-worker-policy.json").read_text(encoding="utf-8"))
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

    def test_synthetic_executor_stage_worker_checks_stay_lightweight(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            state = tmp / "state"
            with (
                patch.object(prt, "load_pipeline_catalog", return_value=PIPELINE_CATALOG),
                patch.object(prt, "load_team_catalog", return_value=TEAM_CATALOG),
            ):
                run_id = "run_executor_perf"
                _, created = call_pipeline([
                    "run",
                    "public_mwp",
                    "--task-id",
                    "executor_perf",
                    "--run-id",
                    run_id,
                    "--request",
                    "executor performance validation",
                    "--state",
                    str(state),
                    "--root",
                    str(ROOT),
                ])
                output = Path(created["run_dir"]) / "outputs" / "orient.md"
                output.write_text(
                    "# orient\n\nDecision: continue.\n\nRisk: low.\n\nNext handoff: status_check.\n\nEvidence: perf loop.\n",
                    encoding="utf-8",
                )
                call_pipeline(["artifact", "add", run_id, "--stage", "orient", "--type", "note", "--path", str(output), "--state", str(state), "--root", str(ROOT)])

                start = time.perf_counter()
                for _ in range(48):
                    code, step = call_pipeline(["executor-step", run_id, "--state", str(state), "--root", str(ROOT)])
            elapsed = time.perf_counter() - start
            gc.collect()

        self.assertEqual(0, code)
        self.assertTrue(step["ready"])
        self.assertEqual(1, step["contract_artifact_count"])
        self.assertLess(elapsed, 3.0)


if __name__ == "__main__":
    unittest.main()
