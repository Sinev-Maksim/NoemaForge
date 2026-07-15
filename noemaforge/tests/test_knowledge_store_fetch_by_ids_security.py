#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_knowledge_store_fetch_by_ids_security.py
Zone: release/package
Version: 0.32.1
Created: 2026-07-15
Modified: 2026-07-15
Purpose: Validate KnowledgeStore fetch_by_ids query selection against SQL injection regressions.
Inputs: Synthetic KnowledgeStore rows in a temporary SQLite database.
Outputs: unittest assertions only.
Side effects: Temporary SQLite stores inside test-owned temp directories.
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

from knowledge.store import KnowledgeStore


class KnowledgeStoreFetchByIdsSecurityTests(unittest.TestCase):
    def test_fetch_by_ids_rejects_table_name_injection(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nfg-kg-fetch-") as tmp:
            store = KnowledgeStore(Path(tmp) / "kg.sqlite")
            source_id = store.add_source(source_id="source:kept", type="book")

            malicious_table = "sources; DELETE FROM sources; --"

            self.assertEqual([], store.fetch_by_ids(malicious_table, [source_id]))
            self.assertEqual("source:kept", store.get_source(source_id)["source_id"])

    def test_fetch_by_ids_uses_fixed_query_for_allowed_table(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nfg-kg-fetch-") as tmp:
            store = KnowledgeStore(Path(tmp) / "kg.sqlite")
            store.add_source(source_id="source:one", type="book")
            store.add_source(source_id="source:two", type="web")

            rows = store.fetch_by_ids("sources", ["source:two", "source:one", "source:two", ""])

            self.assertEqual(["source:two", "source:one"], [row["source_id"] for row in rows])


if __name__ == "__main__":
    unittest.main()
