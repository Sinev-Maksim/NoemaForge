#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_uat_runtime.py
Zone: tests
Purpose: Integration test for the one-command UAT runner (uat_runtime). Verifies
         the full sequence on one pipeline: event recording starts, the pipeline
         runs headless with its artifacts collected into the bundle, recording
         stops, and a manifest + summary are written and returned.
Inputs: uat_runtime + the packaged pipeline catalog.
Outputs: pytest pass/fail.
Side effects: spawns one pipeline run; writes only under a tempdir.
Notes: Code comments are English-only. Headless (--no-gui); the GUI launch is
       exercised on the target host.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import uat_runtime  # noqa: E402

PACKAGE_ROOT = Path(__file__).resolve().parent.parent


class UATRuntimeTests(unittest.TestCase):
    def test_uat_run_records_events_and_bundles_artifacts(self) -> None:
        out = Path(tempfile.mkdtemp(prefix="nf_uat_test_"))
        try:
            rc = uat_runtime.main([
                "run", "--root", str(PACKAGE_ROOT), "--out", str(out),
                "--no-gui", "--pipelines", "public_mwp",
            ])
            self.assertEqual(rc, 0)

            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["kind"], "NoemaForgeUATBundle")
            self.assertEqual(manifest["summary"]["total"], 1)
            self.assertFalse(manifest["gui_launched"])

            # Step 1 + 4: a start and a stop marker were recorded.
            self.assertGreaterEqual(manifest["event_count"], 2)
            self.assertTrue((out / "events" / "events.jsonl").is_file())

            # Step 3: the pipeline ran and its artifacts were collected.
            result = manifest["pipelines"][0]
            self.assertEqual(result["pipeline"], "public_mwp")
            self.assertEqual(result["status"], "ok")
            self.assertGreater(int(result["artifact_count"]), 0)

            self.assertTrue((out / "summary.md").is_file())
            self.assertTrue((out / "pipelines" / "public_mwp" / "run_dir").is_dir())
        finally:
            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
