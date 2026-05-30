#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_events_api_rotation_count.py
Zone: tests
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: Verify that events_api() includes rotation_count in its response and
         that app.js pollEvents() handles rotation detection correctly.
Inputs: AdminGuiServer.events_api() and EventLog.status(); app.js source.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_events_api_rotation_count.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Minimal stubs so admin_gui_server can be imported on Windows without heavy deps
# ---------------------------------------------------------------------------

def _install_stubs() -> None:
    stub_orch = types.ModuleType("orchestration_state")
    stub_orch.nowz = lambda: "2026-05-30T00:00:00Z"
    stub_orch.normalize_session_record = lambda s: dict(s)
    stub_orch.list_active_jobs = lambda *a, **kw: []
    stub_orch.is_active_job = lambda *a, **kw: False
    stub_orch.cancel_job = lambda *a, **kw: False
    stub_orch.OrchestrationState = MagicMock
    sys.modules.setdefault("orchestration_state", stub_orch)

    stub_ss = types.ModuleType("session_store")
    stub_ss.SessionStore = MagicMock
    stub_ss.DEFAULT_SESSION_STATE = Path("/tmp/ss")
    sys.modules.setdefault("session_store", stub_ss)

    stub_el = types.ModuleType("event_log")
    from event_log import EventLog, DEFAULT_EVENT_STATE
    stub_el.EventLog = EventLog
    stub_el.DEFAULT_EVENT_STATE = DEFAULT_EVENT_STATE
    sys.modules["event_log"] = stub_el  # always override to use real EventLog

    stub_jm = types.ModuleType("job_manager")
    stub_jm.JobManager = MagicMock
    sys.modules.setdefault("job_manager", stub_jm)

    stub_ver = types.ModuleType("noemaforge_version")
    stub_ver.RUNTIME_VERSION = "0.32.2"
    sys.modules.setdefault("noemaforge_version", stub_ver)

    stub_core = types.ModuleType("noemaforge_core")
    sys.modules.setdefault("noemaforge_core", stub_core)


_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_install_stubs()

import admin_gui_server  # noqa: E402


# ---------------------------------------------------------------------------
# Helper: build a minimal AdminGuiServer-like object with a real EventLog
# ---------------------------------------------------------------------------

def _make_server(tmp_root: Path):
    """Return a server-like object with real EventLog wired to events_api()."""
    from event_log import EventLog
    with patch("socketserver.TCPServer.__init__", return_value=None), \
         patch("admin_gui_server.SessionStore"), \
         patch("admin_gui_server.EventLog", EventLog):
        server = admin_gui_server.AdminGuiServer.__new__(admin_gui_server.AdminGuiServer)
        server.data_root = tmp_root / "data"
        server.gui_state_dir = tmp_root / "gui"
        server.jobs_dir = tmp_root / "jobs"
        server.session_store = MagicMock()
        server.event_log = EventLog(root=tmp_root / "events")
    return server


# ===========================================================================
# Section 1 — events_api() includes rotation_count
# ===========================================================================

class TestEventsApiIncludesRotationCount(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir)
        self.server = _make_server(self._root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_rotation_count_in_response(self):
        """events_api() must include rotation_count in every success response."""
        result = self.server.events_api(after_index=0)
        self.assertIn("rotation_count", result)

    def test_rotation_count_starts_at_zero(self):
        """rotation_count must be 0 before any rotation has occurred."""
        result = self.server.events_api(after_index=0)
        self.assertEqual(result["rotation_count"], 0)

    def test_rotation_count_matches_event_log_status(self):
        """rotation_count in response must match EventLog.status()."""
        result = self.server.events_api(after_index=0)
        self.assertEqual(result["rotation_count"],
                         self.server.event_log.status()["rotation_count"])

    def test_rotation_count_in_error_response(self):
        """Even on exception, the error response must include rotation_count=0."""
        # Replace event_log with one that always raises
        original = self.server.event_log
        bad_log = MagicMock()
        bad_log.read.side_effect = RuntimeError("disk error")
        bad_log.status.return_value = {"rotation_count": 0}
        self.server.event_log = bad_log
        result = self.server.events_api(after_index=0)
        self.server.event_log = original
        self.assertIn("rotation_count", result)
        self.assertFalse(result["ok"])

    def test_response_includes_ok_events_count(self):
        """Existing fields (ok, events, count) must still be present alongside rotation_count."""
        result = self.server.events_api(after_index=0)
        self.assertTrue(result["ok"])
        self.assertIn("events", result)
        self.assertIn("count", result)

    def test_rotation_count_increments_after_rotation(self):
        """rotation_count in response must increase after a successful log rotation."""
        import json as _json

        # Write enough content to surpass both the fast-path size (1 MB) and the
        # line count threshold (10 000 lines).  Values are derived from the module
        # constants but hardcoded here to avoid importing from the stub module.
        _max_event_lines = 10_000
        _fast_path_bytes = 1024 * 1024
        line = (_json.dumps({"event": "test", "data": "x" * 80}) + "\n").encode("utf-8")
        count = max(_max_event_lines + 1, (_fast_path_bytes // len(line)) + 1)
        self.server.event_log.path.write_bytes(line * count)
        with self.server.event_log._lock:
            self.server.event_log._maybe_rotate()

        result = self.server.events_api(after_index=0)
        self.assertEqual(result["rotation_count"], 1)

    def test_rotation_count_uses_status_if_available(self):
        """events_api() must call event_log.status() when it exists."""
        mock_log = MagicMock()
        mock_log.read.return_value = []
        mock_log.status.return_value = {"rotation_count": 7}
        self.server.event_log = mock_log
        result = self.server.events_api(after_index=0)
        self.assertEqual(result["rotation_count"], 7)
        mock_log.status.assert_called_once()

    def test_rotation_count_zero_when_no_status_method(self):
        """If event_log has no status() method, rotation_count must default to 0."""
        mock_log = MagicMock(spec=["read"])  # no 'status' attribute
        mock_log.read.return_value = []
        self.server.event_log = mock_log
        result = self.server.events_api(after_index=0)
        self.assertEqual(result["rotation_count"], 0)


# ===========================================================================
# Section 2 — app.js source-level checks for rotation detection
# ===========================================================================

class TestAppJsRotationDetection(unittest.TestCase):
    """Verify the pollEvents() function in app.js handles rotation_count."""

    _APP_JS = Path(__file__).resolve().parent.parent / "templates" / "pipeline-dashboard" / "app.js"

    def _get_poll_events_block(self) -> str:
        """Extract the pollEvents function body from app.js."""
        source = self._APP_JS.read_text(encoding="utf-8")
        start = source.index("async function pollEvents()")
        # Find the next top-level async function to bound the block
        try:
            end = source.index("async function ", start + 1)
        except ValueError:
            end = len(source)
        return source[start:end]

    def test_last_rotation_count_variable_declared(self):
        """app.js must declare a lastRotationCount variable."""
        source = self._APP_JS.read_text(encoding="utf-8")
        self.assertIn("lastRotationCount", source,
                      "app.js must declare lastRotationCount for rotation tracking")

    def test_poll_events_checks_rotation_count(self):
        """pollEvents() must reference r.rotation_count."""
        block = self._get_poll_events_block()
        self.assertIn("rotation_count", block,
                      "pollEvents() must check rotation_count from the API response")

    def test_poll_events_resets_last_event_index_on_rotation(self):
        """pollEvents() must reset lastEventIndex to 0 when rotation is detected."""
        block = self._get_poll_events_block()
        self.assertIn("lastEventIndex = 0", block,
                      "pollEvents() must reset lastEventIndex to 0 on rotation")

    def test_poll_events_updates_last_rotation_count(self):
        """pollEvents() must update lastRotationCount after detecting a rotation."""
        block = self._get_poll_events_block()
        self.assertIn("lastRotationCount = r.rotation_count", block,
                      "pollEvents() must update lastRotationCount after reset")


if __name__ == "__main__":
    unittest.main()
