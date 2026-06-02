#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_install_config.py
Zone: tests
Version: 0.32.2
Created: 2026-06-02
Modified: 2026-06-02
Purpose: Tests for install_config.py CLI status handling.
Inputs: install_config.main.
Outputs: unittest assertions only.
Side effects: Creates and removes temporary directories.
Tests: python3 -m unittest noemaforge/tests/test_install_config.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import install_config  # noqa: E402


class TestInstallConfigCli(unittest.TestCase):
    """CLI main() must return non-zero for validation errors, including JSON mode."""

    def test_validate_json_missing_config_returns_error_code(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_install_config_") as tmpdir:
            missing_root = Path(tmpdir) / "missing"
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = install_config.main([
                    "--install-root", str(missing_root),
                    "--validate",
                    "--json",
                ])
        self.assertEqual(1, rc)
        payload = json.loads(out.getvalue())
        self.assertEqual("error", payload["status"])

    def test_env_export_returns_success_code(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nf_install_config_env_") as tmpdir:
            tmp_root = Path(tmpdir)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = install_config.main([
                    "--install-root", str(tmp_root / "noemaforge"),
                    "--data-root", str(tmp_root / "noemaforge-data"),
                    "--env-export", "sh",
                ])
        self.assertEqual(0, rc)
        self.assertIn("NOEMAFORGE_ROOT", out.getvalue())


if __name__ == "__main__":
    unittest.main()
