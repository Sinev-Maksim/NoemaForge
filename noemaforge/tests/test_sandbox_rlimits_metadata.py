#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_sandbox_rlimits_metadata.py
Zone: release/package
Version: 0.32.2
Created: 2026-06-05
Modified: 2026-06-05
Purpose: Validate that sandbox run metadata reports POSIX-rlimit availability.
Inputs: sandbox module API (_run_host, rlimits_available, Quota).
Outputs: unittest assertions only.
Side effects: Spawns a trivial child process in a temporary directory.
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

import sandbox


class SandboxRlimitsMetadataTests(unittest.TestCase):
    def test_rlimits_available_matches_resource_module(self) -> None:
        value = sandbox.rlimits_available()
        self.assertIsInstance(value, bool)
        # True only when the Unix-only 'resource' module is importable (POSIX hosts).
        self.assertEqual(value, sandbox.resource is not None)

    def test_host_meta_reports_rlimits_available(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            rc, _out, err, meta = sandbox._run_host(
                [sys.executable, "-c", "pass"],
                cwd=d,
                env=dict(os.environ),
                quota=sandbox.Quota(),
                network_guard=None,
            )
        self.assertEqual(0, rc, err)
        self.assertEqual("host", meta["backend"])
        self.assertIn("rlimits_available", meta)
        # On the degraded host backend the flag reflects whether POSIX rlimits were enforceable.
        self.assertEqual(meta["rlimits_available"], sandbox.resource is not None)


if __name__ == "__main__":
    unittest.main()
