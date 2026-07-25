#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_startup_profile_recovery.py
Zone: gui/control-plane
Version: see noemaforge_version.py
Created: 2026-07-04
Modified: 2026-07-04
Purpose: Validate Admin GUI startup profile visibility and safe recovery state transitions.
Inputs: AdminGuiServer startup profile state helpers and model profile catalog.
Outputs: unittest assertions only.
Side effects: Writes temporary JSON state under tempfile.TemporaryDirectory().
Tests: python3 -m unittest noemaforge/tests/test_startup_profile_recovery.py -v
Notes: Does not start systemd services, model backends, or first-start.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, str(ROOT / "src"))

import admin_gui_server  # noqa: E402


class StartupProfileRecoveryTests(unittest.TestCase):
    def _server(self, tmp: Path) -> admin_gui_server.AdminGuiServer:
        server = object.__new__(admin_gui_server.AdminGuiServer)
        server.root = ROOT
        server.gui_state_dir = tmp / "gui"
        server.gui_state_dir.mkdir(parents=True, exist_ok=True)
        return server

    def test_safe_minimal_profile_is_always_visible(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            state = self._server(Path(td)).startup_profile_state()

        self.assertEqual("minimal", state["safe_minimal_profile"])
        self.assertIn("minimal", state["profiles"])
        self.assertTrue(state["profiles"]["minimal"]["safe_minimal"])
        self.assertEqual("/api/startup/profile", state["api"]["test_endpoint"])
        self.assertFalse(state["api"]["starts_services"])

    def test_usable_selected_profile_becomes_session_and_last_known(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            server = self._server(Path(td))
            state = server.startup_profile_update({"profile": "research", "usable": True})

        self.assertEqual("research", state["session_profile"])
        self.assertEqual("research", state["active_profile"])
        self.assertEqual("research", state["last_known_usable_profile"])
        self.assertEqual("usable", state["transition"]["state"])
        self.assertIn("usable", state["active_reason"])

    def test_unusable_selected_profile_recovers_to_last_known_usable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            server = self._server(Path(td))
            server.startup_profile_update({"profile": "writer", "usable": True})
            state = server.startup_profile_update({"profile": "gpu-heavy", "usable": False})

        self.assertEqual("writer", state["active_profile"])
        self.assertEqual("writer", state["last_known_usable_profile"])
        self.assertEqual("gpu-heavy", state["transition"]["requested_profile"])
        self.assertEqual("writer", state["transition"]["fallback_profile"])
        self.assertEqual("unusable", state["transition"]["state"])
        self.assertIn("not usable", state["active_reason"])

    def test_string_false_usable_value_is_unusable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            server = self._server(Path(td))
            server.startup_profile_update({"profile": "balanced", "usable": True})
            state = server.startup_profile_update({"profile": "research", "usable": "false"})

        self.assertEqual("balanced", state["active_profile"])
        self.assertEqual("unusable", state["transition"]["state"])
        self.assertFalse(state["profile_status"]["research"])

    def test_unusable_last_known_profile_recovers_to_safe_minimal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            server = self._server(Path(td))
            server.startup_profile_update({"profile": "writer", "usable": True})
            server.startup_profile_update({"profile": "writer", "usable": False})
            state = server.startup_profile_update({"profile": "research", "usable": False})

        self.assertEqual("minimal", state["active_profile"])
        self.assertEqual("minimal", state["last_known_usable_profile"])
        self.assertEqual("minimal", state["transition"]["fallback_profile"])
        self.assertEqual("unusable", state["transition"]["state"])

    def test_testing_selected_profile_preserves_active_until_result(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            server = self._server(Path(td))
            server.startup_profile_update({"profile": "balanced", "usable": True})
            state = server.startup_profile_update({"profile": "research"})

        self.assertEqual("research", state["session_profile"])
        self.assertEqual("balanced", state["active_profile"])
        self.assertEqual("testing", state["transition"]["state"])
        self.assertIn("active profile remains", state["active_reason"])


if __name__ == "__main__":
    unittest.main()
