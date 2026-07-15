#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_roadmap_runtime.py
Zone: release/package
Version: 0.32.1
Created: 2026-07-15
Modified: 2026-07-15
Purpose: Unit-test roadmap runtime database queries and signal filtering.
Inputs: Temporary SQLite roadmap databases.
Outputs: unittest assertions only.
Side effects: Temporary files under the unittest temp directory.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import roadmap


class RoadmapRuntimeTests(unittest.TestCase):
    def test_list_signals_since_filters_by_target_roles(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "roadmap.sqlite")
            roadmap.record_signal(
                target_role="architect",
                key="arch-1",
                requested_by={"stream_id": "dev.work", "role": "qa"},
                title="Architecture item",
                db_path=db_path,
            )
            roadmap.record_signal(
                target_role="surgeon",
                key="surgeon-1",
                requested_by={"stream_id": "dev.work", "role": "qa"},
                title="Surgeon item",
                db_path=db_path,
            )
            roadmap.record_signal(
                target_role="operator",
                key="operator-1",
                requested_by={"stream_id": "ops", "role": "qa"},
                title="Operator item",
                db_path=db_path,
            )

            result = roadmap.list_signals_since(
                since_ts="1970-01-01T00:00:00Z",
                target_roles=["surgeon", "operator"],
                db_path=db_path,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(["surgeon-1", "operator-1"], [signal["key"] for signal in result["signals"]])

    def test_list_signals_since_treats_sql_shaped_role_as_data(self) -> None:
        injected_role = "surgeon') OR 1=1 --"
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "roadmap.sqlite")
            roadmap.record_signal(
                target_role="surgeon",
                key="surgeon-1",
                requested_by={"stream_id": "dev.work", "role": "qa"},
                title="Surgeon item",
                db_path=db_path,
            )
            roadmap.record_signal(
                target_role=injected_role,
                key="literal-role",
                requested_by={"stream_id": "dev.work", "role": "qa"},
                title="Literal role item",
                db_path=db_path,
            )

            result = roadmap.list_signals_since(
                since_ts="1970-01-01T00:00:00Z",
                target_roles=[injected_role],
                db_path=db_path,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(["literal-role"], [signal["key"] for signal in result["signals"]])


if __name__ == "__main__":
    unittest.main()
