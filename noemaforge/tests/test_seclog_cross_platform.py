#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_seclog_cross_platform.py
Zone: tests
Version: see noemaforge_version.py
Created: 2026-06-02
Modified: 2026-06-02
Purpose: Regression test for the cross-platform security log (seclog).
  Verifies seclog imports and operates on hosts WITHOUT POSIX fcntl
  (Windows/macOS dev), that the _flock_* helpers degrade to no-ops, that
  append()+verify() keep the hash chain intact on the no-op-lock path, and
  that SEL_DIR resolves via platform_paths instead of a hardcoded /var/lib path.
Inputs: noemaforge/src/seclog.py.
Outputs: unittest pass/fail.
Side effects: writes/removes files under a tempfile directory.
Tests: py -3 noemaforge/tests/test_seclog_cross_platform.py
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Point the security log at a throwaway directory before importing seclog
# (SEL_DIR is resolved at import time).
_TMP = tempfile.mkdtemp(prefix="nf_seclog_test_")
_SEL_OVERRIDE = str(Path(_TMP) / "sel" / "segments")
_PRIOR_SEL_DIR = os.environ.get("NOEMAFORGE_SEL_DIR")
os.environ["NOEMAFORGE_SEL_DIR"] = _SEL_OVERRIDE

import seclog  # noqa: E402


def tearDownModule() -> None:
    if _PRIOR_SEL_DIR is None:
        os.environ.pop("NOEMAFORGE_SEL_DIR", None)
    else:
        os.environ["NOEMAFORGE_SEL_DIR"] = _PRIOR_SEL_DIR
    shutil.rmtree(_TMP, ignore_errors=True)


class TestSeclogCrossPlatform(unittest.TestCase):
    """seclog must import and operate on POSIX and non-POSIX hosts alike."""

    def test_sel_dir_uses_platform_paths(self) -> None:
        """SEL_DIR is a str honoring the env override (no bare /var/lib default leak)."""
        self.assertIsInstance(seclog.SEL_DIR, str)
        self.assertEqual(seclog.SEL_DIR, _SEL_OVERRIDE)

    def test_flock_helpers_are_noop_without_fcntl(self) -> None:
        """_flock_exclusive/_flock_unlock must not raise when fcntl is absent."""
        original = seclog.fcntl
        seclog.fcntl = None
        try:
            probe = os.path.join(_TMP, "lock_probe.txt")
            with open(probe, "a+", encoding="utf-8") as fh:
                seclog._flock_exclusive(fh)  # no-op, must not raise
                seclog._flock_unlock(fh)
        finally:
            seclog.fcntl = original

    def test_append_and_verify_chain(self) -> None:
        """append() writes records and verify() confirms the hash chain."""
        self.assertTrue(seclog.append({"evt_id": "cp1", "kind": "test", "msg": "alpha"}))
        self.assertTrue(seclog.append({"evt_id": "cp2", "kind": "test", "msg": "beta"}))
        self.assertTrue(seclog.verify())

    def test_append_works_with_fcntl_forced_none(self) -> None:
        """The no-op lock path (non-POSIX host) still yields a verifiable chain."""
        original = seclog.fcntl
        seclog.fcntl = None
        try:
            seclog.append({"evt_id": "cp3", "kind": "test", "msg": "gamma"})
            self.assertTrue(seclog.verify())
        finally:
            seclog.fcntl = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
