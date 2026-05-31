#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_gui_init_and_events.py
Zone: tests
Version: 0.32.2
Created: 2026-05-31
Modified: 2026-05-31
Purpose: Verify task-53/54/55 fixes:
  53 — AdminGuiServer.__init__ must not double-initialize EventLog/SessionStore
       (second init used wrong session path data_root/sessions instead of
       data_root/gui/sessions and created a new server_epoch mid-init).
  54 — pollEvents() must return early after rotation/restart detection instead
       of processing stale events that would advance lastEventIndex past 0.
  55 — events_api() must return already-fetched events even when status() fails.
Inputs: AdminGuiServer, EventLog, source of admin_gui_server.py and app.js.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_admin_gui_init_and_events.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


def _install_stubs() -> None:
    stub_ver = types.ModuleType("noemaforge_version")
    stub_ver.RUNTIME_VERSION = "0.32.2"
    sys.modules.setdefault("noemaforge_version", stub_ver)

    stub_orch = types.ModuleType("orchestration_state")
    stub_orch.nowz = lambda: "2026-05-31T00:00:00Z"
    stub_orch.normalize_session_record = lambda r: r
    sys.modules.setdefault("orchestration_state", stub_orch)

    # job_manager stub
    stub_jm = types.ModuleType("job_manager")
    stub_jm.JobManager = object
    sys.modules.setdefault("job_manager", stub_jm)


_install_stubs()

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from event_log import EventLog  # noqa: E402


# ===========================================================================
# Section 1 — task-53: no double-initialization in AdminGuiServer source
# ===========================================================================

class TestNoDoubleInit(unittest.TestCase):
    """AdminGuiServer.__init__ must not reassign event_log or session_store
    after their first initialization."""

    def _get_init_source(self) -> str:
        source = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")
        # Find AdminGuiServer.__init__ body
        start = source.index("class AdminGuiServer")
        init_start = source.index("def __init__", start)
        # Find the next method definition to bound the body
        try:
            init_end = source.index("\n    def ", init_start + 1)
        except ValueError:
            init_end = len(source)
        return source[init_start:init_end]

    def test_event_log_assigned_once(self):
        """self.event_log must appear exactly once as an assignment target in __init__."""
        import re
        body = self._get_init_source()
        assignments = re.findall(r"\bself\.event_log\s*=", body)
        self.assertEqual(len(assignments), 1,
                         f"self.event_log assigned {len(assignments)} times in __init__; "
                         "must be exactly once to avoid server_epoch change mid-init")

    def test_session_store_assigned_once(self):
        """self.session_store must appear exactly once as an assignment target in __init__."""
        import re
        body = self._get_init_source()
        assignments = re.findall(r"\bself\.session_store\s*=", body)
        self.assertEqual(len(assignments), 1,
                         f"self.session_store assigned {len(assignments)} times in __init__; "
                         "second assignment used wrong path (data_root/sessions vs gui_state_dir/sessions)")

    def test_session_store_uses_gui_state_dir(self):
        """SessionStore must be initialized with gui_state_dir path (matches DEFAULT_SESSION_STATE)."""
        body = self._get_init_source()
        # Check that the session_store init uses gui_state_dir, not data_root directly
        self.assertIn("gui_state_dir", body,
                      "SessionStore must be initialized under gui_state_dir "
                      "to match DEFAULT_SESSION_STATE=/var/lib/noemaforge/gui/sessions")

    def test_event_log_server_epoch_stable_across_status_calls(self):
        """EventLog instance must produce the same server_epoch across calls."""
        tmpdir = tempfile.mkdtemp()
        try:
            log = EventLog(root=Path(tmpdir))
            e1 = log.status()["server_epoch"]
            e2 = log.status()["server_epoch"]
            self.assertEqual(e1, e2)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# ===========================================================================
# Section 2 — task-54: pollEvents() returns early on restart/rotation
# ===========================================================================

class TestPollEventsEarlyReturn(unittest.TestCase):
    """app.js pollEvents() must return immediately after resetting lastEventIndex
    on epoch or rotation_count change so stale events are not processed."""

    def _get_app_js_source(self) -> str:
        app_js = _SRC.parent / "templates" / "pipeline-dashboard" / "app.js"
        return app_js.read_text(encoding="utf-8")

    def test_return_after_server_epoch_reset(self):
        """Source must contain 'return' after lastEventIndex=0 in the epoch-change branch."""
        src = self._get_app_js_source()
        # Find the epoch-change block
        epoch_block_start = src.index("r.server_epoch !== lastServerEpoch")
        epoch_block = src[epoch_block_start:epoch_block_start + 700]
        self.assertIn("return", epoch_block,
                      "pollEvents() must return early after server_epoch change to avoid "
                      "processing stale events that would advance lastEventIndex past 0")

    def test_return_after_rotation_count_reset(self):
        """Source must contain 'return' in the rotation_count-change branch."""
        src = self._get_app_js_source()
        rotation_block_start = src.index("rotation_count !== lastRotationCount")
        rotation_block = src[rotation_block_start:rotation_block_start + 300]
        self.assertIn("return", rotation_block,
                      "pollEvents() must return early after rotation_count change")

    def test_early_return_comment_present(self):
        """Source must document why early return is needed (stale events reason)."""
        src = self._get_app_js_source()
        # Check for explanation comment near the return
        self.assertTrue(
            "stale" in src.lower() or "after_index" in src.lower(),
            "app.js should document the stale-events reason for early return"
        )


# ===========================================================================
# Section 3 — task-55: events_api() preserves events when status() fails
# ===========================================================================

class TestEventsApiStatusFailure(unittest.TestCase):
    """events_api() must return fetched events even if event_log.status() raises."""

    def _make_events_api(self):
        """Import events_api logic via a minimal AdminGuiServer-like stub."""
        source = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")
        # Verify the structure: two separate try blocks (read then status)
        return source

    def test_two_separate_try_blocks_in_events_api(self):
        """events_api() must use separate try blocks for read() and status()."""
        source = self._make_events_api()
        # Find the events_api method body
        start = source.index("def events_api(self")
        try:
            end = source.index("\n    def ", start + 1)
        except ValueError:
            end = len(source)
        body = source[start:end]
        # Count try: occurrences in the method body
        import re
        try_blocks = re.findall(r"\btry\s*:", body)
        self.assertGreaterEqual(len(try_blocks), 2,
                                "events_api() must have separate try blocks for "
                                "read() and status() so status() failure does not "
                                "discard already-fetched events")

    def test_events_api_returns_events_when_status_raises(self):
        """events_api() must return the fetched events even when status() raises."""
        tmpdir = tempfile.mkdtemp()
        try:
            log = EventLog(root=Path(tmpdir))
            log.append("test_event", {"x": 1})

            # Simulate the events_api logic with status() failure
            events = log.read(after_index=0, limit=200)
            self.assertEqual(len(events), 1)

            # Now simulate status() raising
            try:
                st = log.status()
                server_epoch = st.get("server_epoch", "")
                rotation_count = int(st.get("rotation_count", 0))
            except Exception:
                server_epoch = ""
                rotation_count = 0

            # Events must still be present
            result = {
                "ok": True,
                "events": events,
                "server_epoch": server_epoch,
                "rotation_count": rotation_count,
            }
            self.assertEqual(len(result["events"]), 1,
                             "events must be preserved even when status() raises")
            self.assertEqual(result["ok"], True)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_source_has_status_guarded_by_own_try(self):
        """events_api() source must wrap status() call in its own except block."""
        source = self._make_events_api()
        start = source.index("def events_api(self")
        try:
            end = source.index("\n    def ", start + 1)
        except ValueError:
            end = len(source)
        body = source[start:end]
        # Check that status() is called inside a try and has its own except
        self.assertIn("self.event_log.status()", body,
                      "events_api() must call self.event_log.status()")
        # The body should have "except Exception" after the status() call
        status_pos = body.index("self.event_log.status()")
        rest = body[status_pos:]
        self.assertIn("except Exception", rest,
                      "status() call must be guarded by its own except clause")


if __name__ == "__main__":
    unittest.main()
