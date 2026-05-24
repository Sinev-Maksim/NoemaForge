#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_research_packet_performance.py
Zone: release/package
Version: 0.31.13.alpha-patched1
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test Research Packet validation on synthetic packet catalogs.
Inputs: Workspace policy expanded with hundreds of ResearchPacket records.
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
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import research_packet_runtime as rpr


class ResearchPacketPerformanceTests(unittest.TestCase):
    def test_synthetic_research_packet_catalog_validates_under_budget(self) -> None:
        policy = rpr.load_policy(ROOT / "configs" / "research-packet-policy.json")
        base_set = rpr.load_example_set(PROJECT_ROOT / "prelaunch" / "governance" / "research_packet.example.json")
        synthetic_set = copy.deepcopy(base_set)
        base_packets = copy.deepcopy(base_set["packets"])
        base_scoring = copy.deepcopy(base_set["scoring_cases"][0])
        synthetic_set["packets"] = []
        synthetic_set["scoring_cases"] = []
        for index in range(300):
            packet = copy.deepcopy(base_packets[index % len(base_packets)])
            packet["id"] = f"{packet['id']}-{index:03d}"
            packet["trace_id"] = f"{packet['trace_id']}:{index:03d}"
            synthetic_set["packets"].append(packet)
            if index < 100:
                scoring_case = copy.deepcopy(base_scoring)
                scoring_case["id"] = f"{scoring_case['id']}-{index:03d}"
                synthetic_set["scoring_cases"].append(scoring_case)

        started = time.perf_counter()
        with patch.object(rpr, "load_example_set", return_value=synthetic_set):
            report = rpr.validate_research_packet_policy(policy, project_root=PROJECT_ROOT, package_root=ROOT)
        elapsed = time.perf_counter() - started

        self.assertTrue(report["ok"], report["failures"][:10])
        self.assertEqual(300, report["metrics"]["packets"])
        self.assertEqual(300, report["metrics"]["passing_packets"])
        self.assertEqual(100, report["metrics"]["scoring_cases"])
        self.assertEqual(100, report["metrics"]["passing_scoring_cases"])
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
