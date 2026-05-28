#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import firstboot_eval
import model_inventory_normalize as normalizer
import role_tournament


class FirstbootScoringNormalizerRuntimeTests(unittest.TestCase):
    def test_inventory_normalizer_rejects_non_head_shard_records(self) -> None:
        inventory = {
            "models": [
                {"model_id": "alpha", "artifact_format": "gguf", "source_path": "/vault/models/alpha.gguf", "capabilities": ["llm"]},
                {"model_id": "split-head", "artifact_format": "gguf", "source_path": "/vault/models/split-00001-of-00002.gguf", "capabilities": ["llm"]},
                {"model_id": "split-tail", "artifact_format": "gguf", "source_path": "/vault/models/split-00002-of-00002.gguf", "capabilities": ["llm"]},
            ]
        }

        doc = normalizer.normalize_inventory_models(inventory)
        kept_ids = {str(m.get("model_id")) for m in doc["models"]}

        self.assertEqual({"alpha", "split-head"}, kept_ids)
        self.assertEqual(1, doc["normalization"]["rejected_count"])
        self.assertEqual("non_head_shard", doc["normalization"]["rejected_models"][0]["reason"])

    def test_role_tournament_eligibility_uses_normalized_inventory(self) -> None:
        inventory = {
            "models": [
                {"model_id": "split-head", "artifact_format": "gguf", "source_path": "/vault/models/split-00001-of-00002.gguf", "capabilities": ["llm"]},
                {"model_id": "split-tail", "artifact_format": "gguf", "source_path": "/vault/models/split-00002-of-00002.gguf", "capabilities": ["llm"]},
            ]
        }
        roles = {"operator.admin/administrator": {"required_capabilities": ["llm"]}}

        matrix = role_tournament.build_eligibility(inventory, roles)

        self.assertIn("split-head", matrix["models"])
        self.assertNotIn("split-tail", matrix["models"])
        eligible_ids = {str(m.get("model_id")) for m in matrix["roles"]["operator.admin/administrator"]["models"]}
        self.assertEqual({"split-head"}, eligible_ids)

    def test_legacy_firstboot_eval_normalizes_registry_before_scoring(self) -> None:
        registry_models = [
            {"model_id": "alpha", "format": "gguf", "artifact_path": "/modelstore/alpha/model.gguf"},
            {"model_id": "split-head", "format": "gguf", "artifact_path": "/modelstore/split/split-00001-of-00002.gguf"},
            {"model_id": "split-tail", "format": "gguf", "artifact_path": "/modelstore/split/split-00002-of-00002.gguf"},
        ]

        doc = firstboot_eval._normalize_registry_models_for_scoring(registry_models)
        kept_ids = {str(m.get("model_id")) for m in doc["models"]}

        self.assertEqual({"alpha", "split-head"}, kept_ids)
        self.assertEqual(1, doc["normalization"]["rejected_count"])
        self.assertEqual("split-tail", doc["normalization"]["rejected_models"][0]["model_id"])


if __name__ == "__main__":
    unittest.main()
