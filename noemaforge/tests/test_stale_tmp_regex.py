#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_stale_tmp_regex.py
Zone: tests
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: Verify that _STALE_TMP_RE matches both pre-task-34 and post-task-34
         write-atomic tmp file formats while rejecting unrelated .tmp files.
Inputs: _STALE_TMP_RE from admin_gui_server; temporary directories.
Outputs: pytest pass/fail.
Side effects: Writes and removes tmp files under tempfile.mkdtemp().
Tests: pytest noemaforge/tests/test_stale_tmp_regex.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import re
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Minimal stubs so admin_gui_server can be imported without heavy dependencies
# ---------------------------------------------------------------------------
_STUB_NAMES = [
    "orchestration_state",
    "session_store",
    "event_log",
    "job_manager",
    "noemaforge_version",
    "noemaforge_core",
]

def _install_stubs() -> None:
    stub_orch = types.ModuleType("orchestration_state")
    stub_orch.nowz = lambda: "2026-05-30T00:00:00Z"
    stub_orch.normalize_session_record = lambda s: dict(s)
    stub_orch.list_active_jobs = lambda *a, **kw: []
    stub_orch.is_active_job = lambda *a, **kw: False
    stub_orch.cancel_job = lambda *a, **kw: False
    stub_orch.OrchestrationState = MagicMock
    sys.modules["orchestration_state"] = stub_orch

    stub_ss = types.ModuleType("session_store")
    stub_ss.SessionStore = MagicMock
    stub_ss.DEFAULT_SESSION_STATE = Path("/tmp/ss")
    sys.modules["session_store"] = stub_ss

    stub_el = types.ModuleType("event_log")
    stub_el.EventLog = MagicMock
    stub_el.DEFAULT_EVENT_STATE = Path("/tmp/el")
    sys.modules["event_log"] = stub_el

    stub_jm = types.ModuleType("job_manager")
    stub_jm.JobManager = MagicMock
    sys.modules["job_manager"] = stub_jm

    stub_ver = types.ModuleType("noemaforge_version")
    stub_ver.RUNTIME_VERSION = "0.32.2"
    sys.modules["noemaforge_version"] = stub_ver

    stub_core = types.ModuleType("noemaforge_core")
    sys.modules["noemaforge_core"] = stub_core


_install_stubs()

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import admin_gui_server  # noqa: E402  (import after path/stub setup)
from admin_gui_server import _STALE_TMP_RE  # noqa: E402


# ===========================================================================
# Section 1 — regex unit tests (no filesystem)
# ===========================================================================

class TestStaleRegexMatch(unittest.TestCase):
    """_STALE_TMP_RE must match the expected filename patterns."""

    def test_pre_task34_format_matches(self):
        """default.json.tmp (no digits) — pre-task-34 _write_atomic output."""
        self.assertIsNotNone(_STALE_TMP_RE.search("default.json.tmp"))

    def test_pre_task34_arbitrary_session_id_matches(self):
        """my-session-abc.json.tmp also matches."""
        self.assertIsNotNone(_STALE_TMP_RE.search("my-session-abc.json.tmp"))

    def test_post_task34_format_matches(self):
        """default.json.140234567890.tmp (with thread-id digits) — post-task-34."""
        self.assertIsNotNone(_STALE_TMP_RE.search("default.json.140234567890.tmp"))

    def test_post_task34_short_digits_matches(self):
        """default.json.1.tmp (single digit) is still valid."""
        self.assertIsNotNone(_STALE_TMP_RE.search("default.json.1.tmp"))

    def test_post_task34_long_digits_matches(self):
        """Realistic 18-digit thread id."""
        self.assertIsNotNone(_STALE_TMP_RE.search("session-x.json.123456789012345678.tmp"))

    def test_upload_tmp_not_matched(self):
        """upload.tmp must NOT match — no '.json' segment."""
        self.assertIsNone(_STALE_TMP_RE.search("upload.tmp"))

    def test_config_tmp_not_matched(self):
        """config.tmp must NOT match."""
        self.assertIsNone(_STALE_TMP_RE.search("config.tmp"))

    def test_json_without_tmp_not_matched(self):
        """default.json should not trigger a match."""
        self.assertIsNone(_STALE_TMP_RE.search("default.json"))

    def test_bare_tmp_not_matched(self):
        """.tmp alone must not match."""
        self.assertIsNone(_STALE_TMP_RE.search(".tmp"))

    def test_digits_only_tmp_not_matched(self):
        """1234.tmp must not match (no .json segment)."""
        self.assertIsNone(_STALE_TMP_RE.search("1234.tmp"))


# ===========================================================================
# Section 2 — source-level sanity: the compiled regex string is correct
# ===========================================================================

class TestStaleRegexSourcePattern(unittest.TestCase):
    """Verify the constant in source uses the corrected pattern, not the old one."""

    def _get_source_regex_string(self) -> str:
        """Read admin_gui_server.py and extract the _STALE_TMP_RE pattern string."""
        src_path = _SRC / "admin_gui_server.py"
        text = src_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "_STALE_TMP_RE" in line and "re.compile" in line:
                return line
        return ""

    def test_pattern_contains_json_segment(self):
        """Pattern must include '\\.json' to match session files."""
        line = self._get_source_regex_string()
        self.assertIn(r"\.json", line, "Pattern should contain \\.json")

    def test_old_pattern_not_present(self):
        r"""Old vacuous pattern r'\.\d+\.tmp$' must not be the one in use."""
        line = self._get_source_regex_string()
        # The old pattern was exactly r"\.\d+\.tmp$" — it must not appear as
        # the ONLY content between the quotes of re.compile(...)
        self.assertNotIn(r'"\.\d+\.tmp$"', line,
                         "Old wrong pattern must not still be in source")


# ===========================================================================
# Section 3 — functional tests: _cleanup_stale_tmp_files honours both formats
# ===========================================================================

class TestCleanupStaleFilesRegex(unittest.TestCase):
    """_cleanup_stale_tmp_files() must delete both pre- and post-task-34 tmps."""

    def _make_server(self, tmp_root: Path):
        """Return an AdminGuiServer-like object with _cleanup_stale_tmp_files patched paths."""
        with patch("socketserver.TCPServer.__init__", return_value=None), \
             patch("admin_gui_server.SessionStore"), \
             patch("admin_gui_server.EventLog"):
            server = admin_gui_server.AdminGuiServer.__new__(admin_gui_server.AdminGuiServer)
            server.data_root = tmp_root / "data"
            server.gui_state_dir = tmp_root / "gui"
            server.jobs_dir = tmp_root / "jobs"
            server.session_store = MagicMock()
            server.event_log = MagicMock()
        return server

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _plant(self, subdir: str, filename: str) -> Path:
        d = self._root / subdir
        d.mkdir(parents=True, exist_ok=True)
        p = d / filename
        p.write_text("orphan", encoding="utf-8")
        return p

    def test_pre_task34_tmp_deleted(self):
        """default.json.tmp in gui_state_dir is removed."""
        srv = self._make_server(self._root)
        srv.gui_state_dir = self._root / "gui"
        srv.jobs_dir = self._root / "jobs"
        srv.data_root = self._root / "data"
        tmp = self._plant("gui", "default.json.tmp")
        srv._cleanup_stale_tmp_files()
        self.assertFalse(tmp.exists(), "pre-task-34 tmp must be deleted")

    def test_post_task34_tmp_deleted(self):
        """default.json.140234567890.tmp in sessions subdir is removed."""
        srv = self._make_server(self._root)
        srv.gui_state_dir = self._root / "gui"
        srv.jobs_dir = self._root / "jobs"
        srv.data_root = self._root / "data"
        sessions_dir = self._root / "data" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        tmp = sessions_dir / "default.json.140234567890.tmp"
        tmp.write_text("orphan", encoding="utf-8")
        srv._cleanup_stale_tmp_files()
        self.assertFalse(tmp.exists(), "post-task-34 tmp must be deleted")

    def test_unrelated_tmp_preserved(self):
        """upload.tmp must NOT be deleted by the cleanup."""
        srv = self._make_server(self._root)
        srv.gui_state_dir = self._root / "gui"
        srv.jobs_dir = self._root / "jobs"
        srv.data_root = self._root / "data"
        unrelated = self._plant("gui", "upload.tmp")
        srv._cleanup_stale_tmp_files()
        self.assertTrue(unrelated.exists(), "unrelated .tmp must be preserved")

    def test_cleanup_on_missing_dirs_does_not_raise(self):
        """_cleanup_stale_tmp_files() must not raise if a scan dir is absent."""
        srv = self._make_server(self._root)
        srv.gui_state_dir = self._root / "nonexistent_gui"
        srv.jobs_dir = self._root / "nonexistent_jobs"
        srv.data_root = self._root / "nonexistent_data"
        # Must not raise
        srv._cleanup_stale_tmp_files()


if __name__ == "__main__":
    unittest.main()
