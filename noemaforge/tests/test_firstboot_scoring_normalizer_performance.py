#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import model_inventory_normalize as normalizer


class FirstbootScoringNormalizerPerformanceTests(unittest.TestCase):
    def test_large_inventory_normalizes_under_budget(self) -> None:
        models = []
        for index in range(1200):
            models.append({"model_id": f"single-{index}", "artifact_format": "gguf", "source_path": f"/vault/models/single-{index}.gguf", "capabilities": ["llm"]})
            models.append({"model_id": f"tail-{index}", "artifact_format": "gguf", "source_path": f"/vault/models/split-{index}-00002-of-00002.gguf", "capabilities": ["llm"]})

        started = time.perf_counter()
        doc = normalizer.normalize_inventory_models({"models": models})
        elapsed = time.perf_counter() - started

        self.assertEqual(1200, doc["normalization"]["rejected_count"])
        self.assertEqual(1200, len(doc["models"]))
        self.assertLess(elapsed, 1.0, f"normalization took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
