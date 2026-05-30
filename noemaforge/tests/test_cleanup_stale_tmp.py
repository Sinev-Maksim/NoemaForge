#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_cleanup_stale_tmp.py
Zone: test
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: Verify AdminGuiServer._cleanup_stale_tmp_files() removes orphaned *.tmp files on startup.
Inputs: AdminGuiServer._cleanup_stale_tmp_files() via minimal stub.
Outputs: unittest results.
Side effects: None (temp dirs only).
Tests: python -m unittest noemaforge/tests/test_cleanup_stale_tmp.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import admin_gui_server as ags
from admin_gui_server import AdminGuiServer


# ---------------------------------------------------------------------------
# Stub helper
# ---------------------------------------------------------------------------

def _make_stub(tmp_path: Path) -> AdminGuiServer:
    """Build a minimal AdminGuiServer stub with only the dirs needed for cleanup."""
    from event_log import EventLog
    from session_store import SessionStore

    obj = object.__new__(AdminGuiServer)
    obj.gui_state_dir = tmp_path / "gui"
    obj.jobs_dir = tmp_path / "jobs"
    obj.data_root = tmp_path

    # Create the directories so the glob can run.
    for d in [obj.gui_state_dir, obj.jobs_dir, tmp_path / "sessions"]:
        d.mkdir(parents=True, exist_ok=True)

    return obj


# ---------------------------------------------------------------------------
# 1. Cleanup removes *.tmp files
# ---------------------------------------------------------------------------

class TestCleanupStaleTmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tp = Path(self.tmp.name)
        self.srv = _make_stub(self.tp)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tmp_file_in_gui_state_dir_is_removed(self):
        """A *.tmp file directly in gui_state_dir must be deleted."""
        stale = self.srv.gui_state_dir / "conversation-current.json.123456.tmp"
        stale.write_text("{}", encoding="utf-8")

        self.srv._cleanup_stale_tmp_files()

        self.assertFalse(stale.exists(), "Stale tmp file must be removed")

    def test_tmp_file_in_jobs_dir_is_removed(self):
        """A *.tmp file in jobs_dir must be deleted."""
        stale = self.srv.jobs_dir / "job_abc.json.789012.tmp"
        stale.write_text("{}", encoding="utf-8")

        self.srv._cleanup_stale_tmp_files()

        self.assertFalse(stale.exists())

    def test_tmp_file_in_sessions_dir_is_removed(self):
        """A *.tmp file in the sessions sub-dir must be deleted."""
        sessions_dir = self.tp / "sessions"
        stale = sessions_dir / "default.json.111222.tmp"
        stale.write_text("{}", encoding="utf-8")

        self.srv._cleanup_stale_tmp_files()

        self.assertFalse(stale.exists())

    def test_nested_tmp_file_is_removed(self):
        """Stale tmp files in sub-directories are also removed."""
        sub = self.srv.gui_state_dir / "raw"
        sub.mkdir(parents=True, exist_ok=True)
        stale = sub / "msg_001.json.555666.tmp"
        stale.write_text("{}", encoding="utf-8")

        self.srv._cleanup_stale_tmp_files()

        self.assertFalse(stale.exists())

    def test_non_tmp_files_are_untouched(self):
        """Regular (non-*.tmp) files must not be deleted."""
        real_file = self.srv.gui_state_dir / "conversation-current.json"
        real_file.write_text('{"ok": true}', encoding="utf-8")

        self.srv._cleanup_stale_tmp_files()

        self.assertTrue(real_file.exists(), "Real JSON file must not be removed")

    def test_multiple_tmp_files_all_removed(self):
        """All stale tmp files across directories are removed in one call."""
        files = [
            self.srv.gui_state_dir / "a.json.1.tmp",
            self.srv.gui_state_dir / "b.json.2.tmp",
            self.srv.jobs_dir / "c.json.3.tmp",
        ]
        for f in files:
            f.write_text("{}", encoding="utf-8")

        self.srv._cleanup_stale_tmp_files()

        for f in files:
            self.assertFalse(f.exists(), f"{f.name} must be removed")

    def test_no_error_when_dirs_do_not_exist(self):
        """Cleanup must not raise if a scan directory doesn't exist."""
        import shutil
        shutil.rmtree(self.srv.gui_state_dir)

        try:
            self.srv._cleanup_stale_tmp_files()
        except Exception as exc:
            self.fail(f"Unexpected exception: {exc}")

    def test_no_error_when_all_dirs_empty(self):
        """Cleanup on empty dirs must be silent."""
        try:
            self.srv._cleanup_stale_tmp_files()
        except Exception as exc:
            self.fail(f"Unexpected exception: {exc}")


# ---------------------------------------------------------------------------
# 2. Source-text guards
# ---------------------------------------------------------------------------

class TestSourceContainsCleanup(unittest.TestCase):
    SRC_TEXT = (ROOT / "src" / "admin_gui_server.py").read_text(encoding="utf-8")

    def test_method_defined(self):
        self.assertIn("def _cleanup_stale_tmp_files(self)", self.SRC_TEXT)

    def test_called_in_init(self):
        """_cleanup_stale_tmp_files() must be called from __init__."""
        self.assertIn("self._cleanup_stale_tmp_files()", self.SRC_TEXT)

    def test_glob_tmp_pattern(self):
        """Method must use glob('**/*.tmp') to find stale files."""
        self.assertIn('"**/*.tmp"', self.SRC_TEXT)

    def test_unlink_called(self):
        """Method must call unlink to remove found files."""
        self.assertIn(".unlink(", self.SRC_TEXT)

    def test_sessions_dir_in_scan(self):
        """sessions directory must be included in the scan."""
        self.assertIn('"sessions"', self.SRC_TEXT)


if __name__ == "__main__":
    unittest.main()
