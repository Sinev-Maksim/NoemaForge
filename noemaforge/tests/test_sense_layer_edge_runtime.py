#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_sense_layer_edge_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-05-19
Modified: 2026-05-19
Purpose: Validate Sense Layer Edge contracts and offline metric normalization.
Inputs: Workspace Sense Layer Edge policy and local adapter skeletons.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import copy
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

import production_ai_contracts as pac
import sense_layer_edge_runtime as sler
from sense.edge import mqtt_adapter, serial_adapter


class SenseLayerEdgeRuntimeTests(unittest.TestCase):
    def test_workspace_sense_layer_edge_policy_validates(self) -> None:
        policy_path = ROOT / "configs" / "sense-layer-edge.json"
        report = sler.validate_sense_layer_edge_policy(
            sler.load_policy(policy_path),
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(3, report["metrics"]["adapters"])
        self.assertEqual(3, report["metrics"]["passing_adapters"])
        self.assertEqual(1, report["metrics"]["mqtt_adapters"])
        self.assertEqual(1, report["metrics"]["serial_adapters"])
        self.assertEqual(1, report["metrics"]["system_metrics_adapters"])
        self.assertEqual(0, report["metrics"]["live_io_adapters"])
        self.assertEqual(0, report["metrics"]["missing_refs"])

        gate = pac.evaluate_gate(
            {"change_id": "sense-layer-edge-core", "domain": "pipeline"},
            sler.sense_layer_edge_report_to_gate_evidence(report, artifact_uri="reports/sense-layer-edge.json"),
        )
        self.assertTrue(gate["ok"], gate)

    def test_mqtt_and_serial_adapters_normalize_to_one_schema(self) -> None:
        mqtt_metric = mqtt_adapter.normalize_mqtt_message(
            "noemaforge/sense/floor/temperature",
            {"metric_id": "temperature_c", "value": 21.5, "unit": "C"},
            source_id="floor-sensor-bus",
            source_trust="simulated",
        )
        serial_metric = serial_adapter.normalize_serial_line(
            "humidity_pct=47.0 pct",
            source_id="floor-controller-loopback",
            source_trust="trusted",
        )

        for metric in [mqtt_metric, serial_metric]:
            self.assertIn(metric["source_trust"], {"trusted", "simulated", "unverified"})
            self.assertIn(metric["protocol"], {"mqtt", "serial"})
            for field in ["metric_id", "source_id", "source_trust", "timestamp", "value", "unit"]:
                self.assertIn(field, metric)

    def test_trust_schema_live_io_and_required_adapters_are_enforced(self) -> None:
        policy_path = ROOT / "configs" / "sense-layer-edge.json"
        payload = copy.deepcopy(sler.load_policy(policy_path))
        payload["adapters"] = [adapter for adapter in payload["adapters"] if adapter["protocol"] != "serial"]
        mqtt = payload["adapters"][0]
        mqtt["source_trust"] = "implicit"
        mqtt["ingress"]["live_io"] = True
        mqtt["schema_ref"] = "sense/edge/missing_contract.yaml"

        report = sler.validate_sense_layer_edge_policy(
            payload,
            project_root=PROJECT_ROOT,
            package_root=ROOT,
            policy_path=policy_path,
        )

        self.assertFalse(report["ok"])
        self.assertIn("serial_adapter_missing", report["failures"])
        self.assertIn("adapter_source_trust_not_allowed:mqtt-floor-sensors:implicit", report["failures"])
        self.assertIn("adapter_live_io_not_false:mqtt-floor-sensors", report["failures"])
        self.assertIn("adapter_schema_ref_missing:mqtt-floor-sensors:sense/edge/missing_contract.yaml", report["failures"])


if __name__ == "__main__":
    unittest.main()
