#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_previous_install_context_performance.py
Zone: release/package
Version: 0.31.21.alpha
Created: 2026-05-20
Modified: 2026-05-20
Purpose: Performance-test previous-install context validation on synthetic firstboot contexts.
Inputs: Synthetic runtime context dictionaries.
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

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import previous_install_context_runtime as pic
from test_previous_install_context_runtime import valid_context


class PreviousInstallContextPerformanceTests(unittest.TestCase):
    def test_validation_stays_bounded_for_many_contexts(self) -> None:
        policy = pic.load_policy(ROOT / "configs" / "previous-install-context-policy.json")
        contexts = []
        for index in range(2000):
            context = copy.deepcopy(valid_context())
            context["active_runtime"]["bootstrap_state_dir"] = f"/var/lib/noemaforge/bootstrap/run-{index:04d}"
            context["previous_install"]["path"] = f"/var/lib/noemaforge/firstboot-attempt-archive/{index:04d}"
            contexts.append(context)

        started = time.perf_counter()
        reports = [pic.validate_previous_install_context(context, policy=policy) for context in contexts]
        elapsed = time.perf_counter() - started

        self.assertTrue(all(report["ok"] for report in reports))
        self.assertLess(elapsed, 0.75, f"previous install context validation took {elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
