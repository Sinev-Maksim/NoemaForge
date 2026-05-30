#!/usr/bin/env python3
"""
Tests for task-42: Remove duplicate SessionStore/EventLog init in AdminGuiServer.__init__.

Verifies that:
  - session_store is initialized exactly once (to data_root/sessions).
  - event_log is initialized exactly once (to data_root/events).
  - No ghost gui_state_dir/sessions directory is created by a discarded instance.

All tests run offline (source-level analysis + controlled temp-dir checks).
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
# 1. Source-level: count initializations of session_store and event_log
# ---------------------------------------------------------------------------

class TestNoDuplicateInit(unittest.TestCase):

    def _init_src(self) -> str:
        return inspect.getsource(ags.AdminGuiServer.__init__)

    def test_session_store_assigned_exactly_once(self):
        """self.session_store = SessionStore(...) must appear exactly once in __init__."""
        src = self._init_src()
        count = src.count("self.session_store = SessionStore(")
        self.assertEqual(
            count,
            1,
            f"session_store initialized {count} times (expected exactly 1)",
        )

    def test_event_log_assigned_exactly_once(self):
        """self.event_log = EventLog(...) must appear exactly once in __init__."""
        src = self._init_src()
        count = src.count("self.event_log = EventLog(")
        self.assertEqual(
            count,
            1,
            f"event_log initialized {count} times (expected exactly 1)",
        )

    def test_session_store_uses_data_root_sessions(self):
        """The single session_store assignment must use data_root/sessions, not gui_state_dir/sessions."""
        src = self._init_src()
        idx = src.index("self.session_store = SessionStore(")
        block = src[idx: idx + 120]
        self.assertIn(
            'data_root / "sessions"',
            block,
            "session_store does not use data_root/sessions",
        )
        self.assertNotIn(
            "gui_state_dir",
            block,
            "session_store still uses the wrong gui_state_dir/sessions path",
        )

    def test_event_log_uses_data_root_events(self):
        """The single event_log assignment must use data_root/events."""
        src = self._init_src()
        idx = src.index("self.event_log = EventLog(")
        block = src[idx: idx + 80]
        self.assertIn(
            'data_root / "events"',
            block,
            "event_log does not use data_root/events",
        )

    def test_no_ghost_gui_sessions_in_session_store_init(self):
        """gui_state_dir/sessions must NOT appear as an argument to SessionStore() in __init__."""
        src = self._init_src()
        # Collect all SessionStore(...) call sites.
        import re
        calls = re.findall(r"SessionStore\([^)]+\)", src)
        for call in calls:
            self.assertNotIn(
                "gui_state_dir",
                call,
                f"SessionStore call uses wrong gui_state_dir path: {call}",
            )


# ---------------------------------------------------------------------------
# 2. Source-level: session_store defined before super().__init__
# ---------------------------------------------------------------------------

class TestInitOrder(unittest.TestCase):

    def test_session_store_before_super(self):
        src = inspect.getsource(ags.AdminGuiServer.__init__)
        ss_idx = src.find("self.session_store = SessionStore(")
        super_idx = src.find("super().__init__(")
        self.assertGreater(super_idx, ss_idx, "session_store must be assigned before super().__init__")

    def test_event_log_before_super(self):
        src = inspect.getsource(ags.AdminGuiServer.__init__)
        el_idx = src.find("self.event_log = EventLog(")
        super_idx = src.find("super().__init__(")
        self.assertGreater(super_idx, el_idx, "event_log must be assigned before super().__init__")


if __name__ == "__main__":
    unittest.main()
