#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_noema_cli.py
Zone: tests/cli
Version: 0.33.0
Created: 2026-06-07
Modified: 2026-06-07
Purpose: Unit tests for the unified `noema` CLI dispatcher.
Inputs: argv lists; a temp dir for the upgrade subcommand.
Outputs: unittest results.
Side effects: temp dirs only; subcommands invoked in read-only/dry-run modes.
Tests: python3 -m unittest test_noema_cli
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import noema_cli as cli  # noqa: E402


class NoemaCliTests(unittest.TestCase):
    def test_help_returns_zero_and_lists_commands(self):
        for args in ([], ["--help"], ["-h"]):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(args)
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            for cmd in ("doctor", "release", "upgrade"):
                self.assertIn(cmd, out)

    def test_version_prints_runtime_version(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(["--version"])
        self.assertEqual(rc, 0)
        self.assertTrue(buf.getvalue().startswith("noema "))

    def test_unknown_command_returns_2(self):
        buf = io.StringIO()
        with redirect_stderr(buf):
            rc = cli.main(["frobnicate"])
        self.assertEqual(rc, 2)
        self.assertIn("unknown command", buf.getvalue())

    def test_dispatch_doctor(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(["doctor", "--no-admin-probe"])
        self.assertEqual(rc, 0)
        self.assertIn("NoemaForge doctor", buf.getvalue())

    def test_dispatch_release_verify_exit_code(self):
        # A non-existent manifest must make the release subcommand return non-zero via the dispatcher.
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["release", "verify", str(Path(d) / "missing.json"), "--root", d])
            self.assertEqual(rc, 1)

    def test_dispatch_upgrade_plan(self):
        with tempfile.TemporaryDirectory() as cur, tempfile.TemporaryDirectory() as inc:
            (Path(inc) / "x.py").write_text("print(1)", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["upgrade", "plan", "--current", cur, "--incoming", inc])
            self.assertEqual(rc, 0)
            self.assertIn("upgrade plan", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
