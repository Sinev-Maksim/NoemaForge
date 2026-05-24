#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_locale_main_chat_surface_performance.py
Zone: gui/i18n
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Bounded regression test for /api/locales payload generation.
Inputs: Offline locale server fixture.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path


ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import locale_main_chat_surface_runtime as lmcsr


class LocaleMainChatSurfacePerformanceTests(unittest.TestCase):
    def test_locale_payload_generation_is_bounded(self) -> None:
        server = lmcsr.build_offline_locale_server(package_root=ROOT)
        started = time.perf_counter()
        payload = {}
        for _ in range(250):
            payload = server.locales()
        elapsed = time.perf_counter() - started

        self.assertTrue(payload["ok"])
        self.assertEqual(10, len(payload["messages"]))
        self.assertLess(elapsed, 1.5, f"locale payload generation took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
