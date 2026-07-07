#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parents[2]
GATEWAY_SOURCE = REPO / "noemaforge" / "src" / "noemaforge-llm-gateway.go"


class LLMGatewaySourceContractTests(unittest.TestCase):
    def test_gateway_exposes_openai_models_endpoint_without_backend_start(self) -> None:
        source = GATEWAY_SOURCE.read_text(encoding="utf-8")
        self.assertIn('mux.HandleFunc("/v1/models"', source)
        self.assertIn("func handleModels", source)
        self.assertIn('"object":', source)
        self.assertIn('"list"', source)
        self.assertIn('"owned_by"', source)
        self.assertIn('"noemaforge-local"', source)
        self.assertNotIn("systemctl", source[source.index("func handleModels"):source.index("func handleProxy")])


if __name__ == "__main__":
    unittest.main()
