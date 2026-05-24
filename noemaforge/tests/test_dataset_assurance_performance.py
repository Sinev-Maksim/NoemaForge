#!/usr/bin/env python3
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

import dataset_inventory


class DatasetAssurancePerformanceTests(unittest.TestCase):
    def test_existing_seed_assurance_is_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "role_eval_cases"
            target.mkdir()
            for filename in dataset_inventory.REQUIRED_ROLE_EVAL_FILES:
                (target / filename).write_text(json.dumps({"id": filename}) + "\n", encoding="utf-8")

            started = time.perf_counter()
            for _ in range(200):
                report = dataset_inventory.assure_role_eval_dataset(str(target), source_root=str(target), allow_builtin_seed=False)
            elapsed = time.perf_counter() - started

            self.assertTrue(report["ok"], report)
            self.assertLess(elapsed, 1.0, f"200 assurance checks took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
