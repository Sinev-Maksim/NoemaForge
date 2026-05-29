#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_wiki_patch_commit_helper_performance.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test reviewed wiki-patch commit-plan generation.
Inputs: Synthetic patch bundles only.
Outputs: unittest assertions only.
Side effects: Temporary files under unittest temp directories only.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import selftest_runtime as strt


class WikiPatchCommitHelperPerformanceTests(unittest.TestCase):
    def test_synthetic_commit_plan_generation_stays_lightweight(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            patch_dir = tmp / "patch"
            wiki_repo = tmp / "wiki"
            (patch_dir / "payload").mkdir(parents=True)
            wiki_repo.mkdir()
            (patch_dir / "apply.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            (patch_dir / "wiki_patch_manifest.json").write_text(json.dumps({"patch_id": "perf_patch"}), encoding="utf-8")
            start = time.perf_counter()
            for index in range(80):
                plan = strt.build_wiki_patch_commit_plan(
                    patch_dir,
                    wiki_repo,
                    branch=f"noemaforge/wiki/perf-{index}",
                    reviewed_by="operator",
                    review_id=f"review-{index}",
                    out_dir=tmp / f"plan-{index}",
                )
            elapsed = time.perf_counter() - start

        self.assertTrue(plan["no_push"])
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
