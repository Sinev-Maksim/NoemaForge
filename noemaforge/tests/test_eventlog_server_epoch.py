#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_eventlog_server_epoch.py
Zone: tests
Version: 0.32.2
Created: 2026-05-31
Modified: 2026-05-31
Purpose: Verify EventLog.status() exposes a stable server_epoch that changes
         across instances, so remote pollers can detect server restarts even
         when rotation_count stays at 0.
Inputs: EventLog from event_log; source text of event_log.py and app.js.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_eventlog_server_epoch.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _install_stubs() -> None:
    import noemaforge_version as real_version
    sys.modules.setdefault("noemaforge_version", real_version)

    stub_orch = types.ModuleType("orchestration_state")
    stub_orch.nowz = lambda: "2026-05-31T00:00:00Z"
    sys.modules.setdefault("orchestration_state", stub_orch)


_install_stubs()

from event_log import EventLog  # noqa: E402


# ===========================================================================
# Section 1 — server_epoch present and well-formed
# ===========================================================================

class TestServerEpochPresence(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.log = EventLog(root=Path(self._tmpdir))

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_status_has_server_epoch(self):
        """status() dict must contain 'server_epoch' key."""
        st = self.log.status()
        self.assertIn("server_epoch", st, "status() must include server_epoch")

    def test_server_epoch_is_string(self):
        """server_epoch must be a non-empty string."""
        epoch = self.log.status()["server_epoch"]
        self.assertIsInstance(epoch, str)
        self.assertTrue(len(epoch) > 0, "server_epoch must not be empty")

    def test_server_epoch_is_hex(self):
        """server_epoch must be a valid hex string (UUID4 hex)."""
        epoch = self.log.status()["server_epoch"]
        try:
            int(epoch, 16)
        except ValueError:
            self.fail(f"server_epoch {epoch!r} is not a valid hex string")

    def test_server_epoch_length_32(self):
        """server_epoch must be 32 hex characters (uuid4().hex)."""
        epoch = self.log.status()["server_epoch"]
        self.assertEqual(len(epoch), 32,
                         f"server_epoch should be 32 chars, got {len(epoch)}")


# ===========================================================================
# Section 2 — stability within a single instance
# ===========================================================================

class TestServerEpochStability(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.log = EventLog(root=Path(self._tmpdir))

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_epoch_stable_across_status_calls(self):
        """server_epoch must not change between consecutive status() calls."""
        e1 = self.log.status()["server_epoch"]
        e2 = self.log.status()["server_epoch"]
        self.assertEqual(e1, e2, "server_epoch must be stable within one EventLog instance")

    def test_epoch_stable_after_append(self):
        """server_epoch must not change after log entries are written."""
        e_before = self.log.status()["server_epoch"]
        self.log.append("test_event", {"data": "x"})
        e_after = self.log.status()["server_epoch"]
        self.assertEqual(e_before, e_after, "server_epoch must not change after append()")

    def test_epoch_stable_after_rotation(self):
        """server_epoch must remain constant after a rotation."""
        import json
        e_before = self.log.status()["server_epoch"]
        # Force rotation by writing enough lines
        line = (json.dumps({"event": "t", "data": "x" * 80}) + "\n").encode("utf-8")
        count = max(10_001, (1024 * 1024 // len(line)) + 1)
        self.log.path.write_bytes(line * count)
        with self.log._lock:
            self.log._maybe_rotate()
        e_after = self.log.status()["server_epoch"]
        self.assertEqual(e_before, e_after,
                         "server_epoch must not change when rotation_count increments")


# ===========================================================================
# Section 3 — changes across instances (simulating server restart)
# ===========================================================================

class TestServerEpochChangesAcrossInstances(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._root = Path(self._tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_new_instance_has_different_epoch(self):
        """Two separate EventLog instances must have distinct server_epoch values."""
        log1 = EventLog(root=self._root)
        log2 = EventLog(root=self._root)
        e1 = log1.status()["server_epoch"]
        e2 = log2.status()["server_epoch"]
        self.assertNotEqual(e1, e2,
                            "Different EventLog instances must have distinct server_epoch "
                            "(simulates server restart detection)")

    def test_restart_detected_by_epoch_change(self):
        """Simulated restart: rotation_count stays 0, but epoch changes → reset fires."""
        log1 = EventLog(root=self._root)
        epoch1 = log1.status()["server_epoch"]
        count1 = log1.status()["rotation_count"]
        self.assertEqual(count1, 0)

        # Simulate restart: new instance, no rotations performed.
        log2 = EventLog(root=self._root)
        epoch2 = log2.status()["server_epoch"]
        count2 = log2.status()["rotation_count"]
        self.assertEqual(count2, 0)

        # rotation_count is same in both (0), but epoch differs → restart detected.
        self.assertEqual(count1, count2,
                         "rotation_count stays 0 across restart — this is the problematic case")
        self.assertNotEqual(epoch1, epoch2,
                            "server_epoch differs → poller can detect restart even though "
                            "rotation_count did not change")


# ===========================================================================
# Section 4 — source guard: server_epoch in status() docstring
# ===========================================================================

class TestServerEpochDocumented(unittest.TestCase):

    def _get_status_docstring(self) -> str:
        source = (_SRC / "event_log.py").read_text(encoding="utf-8")
        method_start = source.index("def status(self)")
        doc_start = source.index('"""', method_start)
        doc_end = source.index('"""', doc_start + 3) + 3
        return source[doc_start:doc_end]

    def test_server_epoch_in_status_docstring(self):
        """status() docstring must document the server_epoch key."""
        doc = self._get_status_docstring()
        self.assertIn("server_epoch", doc,
                      "status() docstring must document the server_epoch key")

    def test_restart_detection_mentioned_in_docstring(self):
        """status() docstring must explain the restart-detection use of server_epoch."""
        doc = self._get_status_docstring()
        self.assertTrue(
            "restart" in doc.lower() or "process" in doc.lower(),
            "status() docstring must explain server_epoch is for restart detection"
        )

    def test_app_js_has_last_server_epoch(self):
        """app.js must declare lastServerEpoch for restart detection."""
        app_js = (_SRC.parent / "templates" / "pipeline-dashboard" / "app.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("lastServerEpoch", app_js,
                      "app.js must track lastServerEpoch to detect server restarts")

    def test_app_js_resets_on_epoch_change(self):
        """app.js pollEvents() must reset lastEventIndex when server_epoch changes."""
        app_js = (_SRC.parent / "templates" / "pipeline-dashboard" / "app.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("r.server_epoch", app_js,
                      "app.js must compare r.server_epoch to detect restarts")


if __name__ == "__main__":
    unittest.main()
