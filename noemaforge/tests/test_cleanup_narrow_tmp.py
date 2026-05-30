#!/usr/bin/env python3
"""
Tests for task-39: _cleanup_stale_tmp_files() with narrow _STALE_TMP_RE pattern.

Verifies that:
  - Only files matching {basename}.{digits}.tmp are removed (thread-unique pattern).
  - Legitimate .tmp files (no digit stem) are left untouched.
  - The _STALE_TMP_RE regex is defined at module level and used as the filter.
  - Missing directories are handled gracefully (no crash).

All tests run offline with temp-dir isolation.
"""
from __future__ import annotations

import inspect
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap import path.
# ---------------------------------------------------------------------------
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import types

# Stub every heavy dependency AdminGuiServer imports.
for mod_name, attrs in [
    ("orchestration_state", {"nowz": lambda: "2026-01-01T00:00:00Z", "OrchestrationState": None, "is_active_job": lambda *a, **kw: False}),
    ("noemaforge_version", {"RUNTIME_VERSION": "0.32.2"}),
    ("job_manager", {"JobManager": None, "JobStatus": None}),
    ("session_store", {"SessionStore": None}),
    ("event_log", {"EventLog": None}),
    ("startup_preflight", {"PreflightSuite": None}),
    ("config_validator", {"ConfigValidator": None}),
]:
    if mod_name not in sys.modules:
        m = types.ModuleType(mod_name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[mod_name] = m


# Patch ThreadingHTTPServer so we can import without binding a socket.
import http.server

_real_threading_http = http.server.ThreadingHTTPServer


class _FakeThreadingHTTPServer:
    def __init__(self, *a, **kw):
        pass


http.server.ThreadingHTTPServer = _FakeThreadingHTTPServer  # type: ignore

# Now we can safely import without instantiating.
import importlib
import admin_gui_server as ags

# Restore the real class so other tests are not affected.
http.server.ThreadingHTTPServer = _real_threading_http  # type: ignore


# ---------------------------------------------------------------------------
# 1. Module-level _STALE_TMP_RE constant
# ---------------------------------------------------------------------------

class TestRegexConstant(unittest.TestCase):

    def test_stale_tmp_re_defined(self):
        self.assertTrue(hasattr(ags, "_STALE_TMP_RE"), "_STALE_TMP_RE not found in admin_gui_server")

    def test_regex_matches_thread_unique_tmp(self):
        pattern = ags._STALE_TMP_RE
        # Standard thread-unique names produced by _write_json/_write_atomic.
        self.assertIsNotNone(pattern.search("conversation-current.json.140234567890.tmp"))
        self.assertIsNotNone(pattern.search("state.json.1.tmp"))
        self.assertIsNotNone(pattern.search("data.12345.tmp"))

    def test_regex_does_not_match_bare_tmp(self):
        pattern = ags._STALE_TMP_RE
        # Plain .tmp files — not thread-unique; must be preserved.
        self.assertIsNone(pattern.search("upload.tmp"))
        self.assertIsNone(pattern.search("config.tmp"))
        self.assertIsNone(pattern.search("something.tmp"))

    def test_regex_does_not_match_alpha_suffix(self):
        pattern = ags._STALE_TMP_RE
        # Non-digit stems must not be matched.
        self.assertIsNone(pattern.search("foo.bar.tmp"))
        self.assertIsNone(pattern.search("job.abc.tmp"))

    def test_regex_used_in_cleanup_source(self):
        """_cleanup_stale_tmp_files must reference _STALE_TMP_RE (not use glob alone)."""
        src = inspect.getsource(ags.AdminGuiServer._cleanup_stale_tmp_files)
        self.assertIn("_STALE_TMP_RE", src, "_cleanup_stale_tmp_files does not use _STALE_TMP_RE")


# ---------------------------------------------------------------------------
# 2. Functional cleanup behaviour
# ---------------------------------------------------------------------------

class TestCleanupBehaviour(unittest.TestCase):
    """Use _cleanup_stale_tmp_files() as a standalone function via a minimal
    AdminGuiServer-shaped object to avoid full server construction."""

    def _run_cleanup(self, scan_dirs: list[Path]) -> None:
        """Call the cleanup logic with a mock server that owns the given dirs."""

        class _MockServer:
            gui_state_dir = scan_dirs[0] if len(scan_dirs) > 0 else Path("/nonexistent-a")
            jobs_dir = scan_dirs[1] if len(scan_dirs) > 1 else Path("/nonexistent-b")
            data_root = scan_dirs[2].parent if len(scan_dirs) > 2 else Path("/nonexistent-c")

            def __init__(self_inner):
                # Override data_root / "sessions" to point to scan_dirs[2].
                if len(scan_dirs) > 2:
                    self_inner.data_root = type("_DR", (), {
                        "__truediv__": lambda s, other: scan_dirs[2] if other == "sessions" else Path("/nonexistent") / other
                    })()

        mock = _MockServer()
        ags.AdminGuiServer._cleanup_stale_tmp_files(mock)

    def test_thread_unique_tmp_removed(self):
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d)
            # Create thread-unique tmp files.
            stale = dp / "state.json.140234567890.tmp"
            stale.write_text("stale")
            another = dp / "sub" / "jobs.json.9999.tmp"
            another.parent.mkdir()
            another.write_text("stale2")

            class _M:
                gui_state_dir = dp
                jobs_dir = dp / "NOEXIST"
                data_root = type("_DR", (), {
                    "__truediv__": lambda s, k: dp / "NOEXIST2" if k == "sessions" else dp / k
                })()

            ags.AdminGuiServer._cleanup_stale_tmp_files(_M())
            self.assertFalse(stale.exists(), "Thread-unique .tmp was NOT removed")
            self.assertFalse(another.exists(), "Nested thread-unique .tmp was NOT removed")

    def test_plain_tmp_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d)
            legit = dp / "upload.tmp"
            legit.write_text("legit")
            also_legit = dp / "foo.bar.tmp"
            also_legit.write_text("legit2")

            class _M:
                gui_state_dir = dp
                jobs_dir = dp / "NOEXIST"
                data_root = type("_DR", (), {
                    "__truediv__": lambda s, k: dp / "NOEXIST2"
                })()

            ags.AdminGuiServer._cleanup_stale_tmp_files(_M())
            self.assertTrue(legit.exists(), "Plain upload.tmp was incorrectly deleted")
            self.assertTrue(also_legit.exists(), "foo.bar.tmp was incorrectly deleted")

    def test_missing_directory_no_crash(self):
        """Directories that do not exist must be skipped gracefully."""

        class _M:
            gui_state_dir = Path("/nonexistent-gui-dir-task39")
            jobs_dir = Path("/nonexistent-jobs-dir-task39")
            data_root = type("_DR", (), {
                "__truediv__": lambda s, k: Path("/nonexistent-sess-dir-task39")
            })()

        # Must not raise.
        ags.AdminGuiServer._cleanup_stale_tmp_files(_M())

    def test_thread_unique_and_plain_coexist(self):
        """Only thread-unique files are removed; plain ones survive in the same dir."""
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d)
            stale = dp / "data.123456789.tmp"
            stale.write_text("stale")
            keep = dp / "scratch.tmp"
            keep.write_text("keep")

            class _M:
                gui_state_dir = dp
                jobs_dir = dp / "NOEXIST"
                data_root = type("_DR", (), {
                    "__truediv__": lambda s, k: dp / "NOEXIST2"
                })()

            ags.AdminGuiServer._cleanup_stale_tmp_files(_M())
            self.assertFalse(stale.exists())
            self.assertTrue(keep.exists())

    def test_cleanup_called_in_init_source(self):
        """__init__ must invoke _cleanup_stale_tmp_files()."""
        src = inspect.getsource(ags.AdminGuiServer.__init__)
        self.assertIn(
            "_cleanup_stale_tmp_files",
            src,
            "__init__ does not call _cleanup_stale_tmp_files()",
        )


if __name__ == "__main__":
    unittest.main()
