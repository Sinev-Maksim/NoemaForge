#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_noema_start.py
Zone: tests/cli
Version: 0.33.0
Created: 2026-06-07
Modified: 2026-06-07
Purpose: Unit tests for noema_start (one-button start). Verifies the pure plan, best-effort dir
  creation, readiness gating, --check-only (no side effects), and the launch path via injected
  hooks (no real server/browser).
Inputs: temp dirs + fakes.
Outputs: unittest results.
Side effects: temp dirs only; never launches a real server.
Tests: python3 -m unittest test_noema_start
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
import io
import json
import sys
import tempfile
import unittest
import unittest.mock as mock
from contextlib import redirect_stdout
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import noema_start as ns  # noqa: E402


class FakePaths:
    gui_listen_address = ("127.0.0.1", 8799)

    def __init__(self, base: Path):
        self.data_root = base / "data"
        self.gui_state_dir = base / "data" / "gui"
        self.session_state_dir = base / "data" / "sessions"
        self.model_selection_state_dir = base / "data" / "model-selection"


class FakeProc:
    def __init__(self, *, exits=None):
        self.pid = 4242
        self._waited = False
        self._exits = exits  # None => stays running

    def poll(self):
        return self._exits

    def wait(self):
        self._waited = True
        return 0


class NoemaStartTests(unittest.TestCase):
    def test_build_start_plan_uses_paths(self):
        with tempfile.TemporaryDirectory() as t:
            plan = ns.build_start_plan(root=Path(t), paths=FakePaths(Path(t)))
        self.assertEqual(plan["host"], "127.0.0.1")
        self.assertEqual(plan["port"], 8799)
        self.assertEqual(plan["url"], "http://127.0.0.1:8799/")
        self.assertIn("admin_gui_server.py", plan["server"])
        self.assertIn("--port", plan["launch_argv"])
        self.assertIn("8799", plan["launch_argv"])
        self.assertTrue(any(p.endswith("sessions") for p in plan["data_dirs"]))

    def test_build_start_plan_defaults_when_paths_unavailable(self):
        # When platform_paths cannot be loaded, fall back to localhost:8765 and no data dirs.
        with mock.patch.object(ns, "_default_paths", return_value=None):
            plan = ns.build_start_plan()
        self.assertEqual((plan["host"], plan["port"]), ("127.0.0.1", 8765))
        self.assertEqual(plan["data_dirs"], [])

    def test_explicit_host_port_override(self):
        plan = ns.build_start_plan(host="127.0.0.1", port=9001, paths=None)
        self.assertEqual(plan["port"], 9001)
        self.assertEqual(plan["url"], "http://127.0.0.1:9001/")

    def test_ensure_dirs_creates_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as t:
            plan = ns.build_start_plan(root=Path(t), paths=FakePaths(Path(t)))
            r1 = ns.ensure_dirs(plan)
            r2 = ns.ensure_dirs(plan)  # idempotent
            self.assertTrue(all(Path(d).is_dir() for d in plan["data_dirs"]))
            self.assertEqual(r1["skipped"], [])
            self.assertEqual(r2["skipped"], [])

    def test_ensure_dirs_skips_unwritable_without_raising(self):
        with tempfile.TemporaryDirectory() as t:
            blocker = Path(t) / "afile"
            blocker.write_text("x", encoding="utf-8")
            plan = {"data_dirs": [str(blocker / "sub")]}  # mkdir under a file -> OSError
            res = ns.ensure_dirs(plan)
        self.assertEqual(res["created"], [])
        self.assertEqual(len(res["skipped"]), 1)

    def test_check_only_has_no_side_effects(self):
        with tempfile.TemporaryDirectory() as t:
            # --no-doctor avoids importing the real doctor; --check-only must not create/launch.
            with mock.patch.object(ns, "_spawn", side_effect=AssertionError("must not spawn")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = ns.main(["--root", t, "--no-doctor", "--check-only", "--json"])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertIn("plan", payload)
            self.assertEqual(payload["ensured"], None)

    def test_launch_spawns_and_opens_browser(self):
        plan = ns.build_start_plan(host="127.0.0.1", port=8765, paths=None)
        opened = []
        # Port closed during startup loop, then opens once -> triggers browser + proceeds.
        port_states = iter([False, True, True])
        with mock.patch.object(ns, "_spawn", return_value=FakeProc()) as spawn, \
                mock.patch.object(ns, "_open_browser", lambda u: opened.append(u)), \
                mock.patch.object(ns, "_port_open", lambda h, p, timeout=0.5: next(port_states)), \
                mock.patch.object(ns.time, "sleep", lambda *_: None):
            rc = ns.launch(plan, open_browser=True, wait=True)
        self.assertEqual(rc, 0)
        spawn.assert_called_once_with(plan["launch_argv"])
        self.assertEqual(opened, [plan["url"]])

    def test_launch_attaches_to_already_running(self):
        plan = ns.build_start_plan(host="127.0.0.1", port=8765, paths=None)
        opened = []
        with mock.patch.object(ns, "_spawn", side_effect=AssertionError("must not spawn")), \
                mock.patch.object(ns, "_open_browser", lambda u: opened.append(u)), \
                mock.patch.object(ns, "_port_open", lambda h, p, timeout=0.5: True):
            rc = ns.launch(plan, open_browser=True, wait=True)
        self.assertEqual(rc, 0)
        self.assertEqual(opened, [plan["url"]])

    def test_critical_readiness_blocks_without_force(self):
        with tempfile.TemporaryDirectory() as t:
            with mock.patch.object(ns, "readiness",
                                   return_value={"ok": False, "summary": {"critical": 2}}), \
                    mock.patch.object(ns, "_spawn", side_effect=AssertionError("must not spawn")):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = ns.main(["--root", t])
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
