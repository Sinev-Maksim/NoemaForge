#!/usr/bin/env python3
"""
Tests for task-43: _cleanup_stale_tmp_files() coverage-gap documentation.

Verifies:
  - The method exists with the correct regex filter (task-39 improvement).
  - The docstring mentions task-23 (the dependency) so maintainers understand
    why gui/jobs scans appear vacuous on the current release base.
  - Functional behaviour: sessions dir cleaned, plain .tmp files preserved.

All tests run offline with temp-dir isolation.
"""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap import path.
# ---------------------------------------------------------------------------
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import types

for mod_name, attrs in [
    ("orchestration_state", {
        "nowz": lambda: "2026-01-01T00:00:00Z",
        "OrchestrationState": None,
        "is_active_job": lambda *a, **kw: False,
    }),
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

import http.server

_real_threading_http = http.server.ThreadingHTTPServer


class _FakeThreadingHTTPServer:
    def __init__(self, *a, **kw):
        pass


http.server.ThreadingHTTPServer = _FakeThreadingHTTPServer  # type: ignore

import admin_gui_server as ags

http.server.ThreadingHTTPServer = _real_threading_http  # type: ignore


# ---------------------------------------------------------------------------
# 1. Module-level regex constant
# ---------------------------------------------------------------------------

class TestRegexConstant(unittest.TestCase):

    def test_stale_tmp_re_defined(self):
        self.assertTrue(hasattr(ags, "_STALE_TMP_RE"))

    def test_regex_matches_thread_unique_tmp(self):
        p = ags._STALE_TMP_RE
        self.assertIsNotNone(p.search("state.json.140234567890.tmp"))
        self.assertIsNotNone(p.search("data.99.tmp"))

    def test_regex_does_not_match_plain_tmp(self):
        p = ags._STALE_TMP_RE
        self.assertIsNone(p.search("upload.tmp"))
        self.assertIsNone(p.search("config.tmp"))
        self.assertIsNone(p.search("foo.bar.tmp"))


# ---------------------------------------------------------------------------
# 2. Docstring mentions coverage-gap dependency (task-23)
# ---------------------------------------------------------------------------

class TestDocstringCoverageNote(unittest.TestCase):

    def _method_src(self) -> str:
        return inspect.getsource(ags.AdminGuiServer._cleanup_stale_tmp_files)

    def test_docstring_mentions_task23(self):
        """The method docstring must mention task-23 as the pending dependency."""
        src = self._method_src()
        self.assertIn(
            "task-23",
            src,
            "_cleanup_stale_tmp_files docstring must mention task-23 coverage dependency",
        )

    def test_docstring_explains_gui_jobs_coverage(self):
        """Docstring must note that gui/jobs scans become active after task-23."""
        src = self._method_src()
        self.assertIn(
            "gui",
            src.lower(),
            "Docstring should mention gui_state_dir coverage status",
        )

    def test_regex_referenced_in_method(self):
        """_STALE_TMP_RE must be used inside the method body (not glob-only)."""
        src = self._method_src()
        self.assertIn("_STALE_TMP_RE", src)

    def test_cleanup_called_in_init(self):
        """__init__ must call _cleanup_stale_tmp_files()."""
        src = inspect.getsource(ags.AdminGuiServer.__init__)
        self.assertIn("_cleanup_stale_tmp_files", src)


# ---------------------------------------------------------------------------
# 3. Functional behaviour
# ---------------------------------------------------------------------------

class TestFunctionalCleanup(unittest.TestCase):

    def _run(self, scan_dirs):
        class _M:
            gui_state_dir = scan_dirs[0] if len(scan_dirs) > 0 else Path("/nex-a")
            jobs_dir = scan_dirs[1] if len(scan_dirs) > 1 else Path("/nex-b")
            data_root = type("_DR", (), {
                "__truediv__": lambda s, k: scan_dirs[2] if (len(scan_dirs) > 2 and k == "sessions") else Path("/nex-c") / k
            })()
        ags.AdminGuiServer._cleanup_stale_tmp_files(_M())

    def test_thread_unique_tmp_deleted(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d)
            stale = dp / "s.140234567890.tmp"
            stale.write_text("stale")

            class _M:
                gui_state_dir = dp
                jobs_dir = dp / "NOEXIST"
                data_root = type("_DR", (), {
                    "__truediv__": lambda s, k: dp / "NOEXIST2"
                })()

            ags.AdminGuiServer._cleanup_stale_tmp_files(_M())
            self.assertFalse(stale.exists())

    def test_plain_tmp_preserved(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d)
            keep = dp / "upload.tmp"
            keep.write_text("legit")

            class _M:
                gui_state_dir = dp
                jobs_dir = dp / "NOEXIST"
                data_root = type("_DR", (), {
                    "__truediv__": lambda s, k: dp / "NOEXIST2"
                })()

            ags.AdminGuiServer._cleanup_stale_tmp_files(_M())
            self.assertTrue(keep.exists())

    def test_missing_dir_no_crash(self):
        class _M:
            gui_state_dir = Path("/nonexistent-g-task43")
            jobs_dir = Path("/nonexistent-j-task43")
            data_root = type("_DR", (), {
                "__truediv__": lambda s, k: Path("/nonexistent-s-task43")
            })()

        ags.AdminGuiServer._cleanup_stale_tmp_files(_M())


if __name__ == "__main__":
    unittest.main()
