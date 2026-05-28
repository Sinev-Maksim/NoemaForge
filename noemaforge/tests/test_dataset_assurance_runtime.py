#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import dataset_inventory


class DatasetAssuranceRuntimeTests(unittest.TestCase):
    def test_builtin_seed_repairs_missing_role_eval_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "role_eval_cases"

            report = dataset_inventory.assure_role_eval_dataset(str(target), source_root=str(Path(tmp) / "missing-source"))

            self.assertTrue(report["ok"], report)
            self.assertEqual(4, len(report["written"]))
            self.assertEqual([], report["after"]["missing_required_files"])
            self.assertGreaterEqual(report["after"]["record_count"], 40)
            for filename in dataset_inventory.REQUIRED_ROLE_EVAL_FILES:
                with (target / filename).open("r", encoding="utf-8") as f:
                    self.assertIsInstance(json.loads(f.readline()), dict)

    def test_source_seed_copy_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            target = Path(tmp) / "target"
            source.mkdir()
            for filename in dataset_inventory.REQUIRED_ROLE_EVAL_FILES:
                (source / filename).write_text(json.dumps({"id": filename}) + "\n", encoding="utf-8")

            first = dataset_inventory.assure_role_eval_dataset(str(target), source_root=str(source), allow_builtin_seed=False)
            second = dataset_inventory.assure_role_eval_dataset(str(target), source_root=str(source), allow_builtin_seed=False)

            self.assertTrue(first["ok"], first)
            self.assertEqual(4, len(first["copied"]))
            self.assertTrue(second["ok"], second)
            self.assertEqual([], second["copied"])
            self.assertEqual([], second["written"])


if __name__ == "__main__":
    unittest.main()
