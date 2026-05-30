#!/usr/bin/env python3
"""
Tests for task-40: Fix falsy session_id substitution in POST /api/session/mode.

Verifies that 'or "default"' is replaced with an explicit is-None check so
that legitimate falsy values (0, False, empty list []) are not silently mapped
to the "default" session.

All tests run offline against source code (no live server required).
"""
from __future__ import annotations

import inspect
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

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

AdminGuiHandler = ags.AdminGuiHandler


# ---------------------------------------------------------------------------
# Minimal handler harness (shared by existing test suites)
# ---------------------------------------------------------------------------

def make_handler(server_mock=None):
    """Return an AdminGuiHandler instance wired to a mock server."""
    if server_mock is None:
        server_mock = MagicMock()
        server_mock.session_set_mode.return_value = {"ok": True}

    class FakeRequest:
        def makefile(self, *a, **kw):
            return io.BytesIO()

    handler = AdminGuiHandler.__new__(AdminGuiHandler)
    handler.server = server_mock
    handler.headers = {}
    handler.client_address = ("127.0.0.1", 9999)
    handler.request = FakeRequest()
    handler._responses: list[tuple[int, dict]] = []

    def _send_json(data, status=200):
        handler._responses.append((status, data))

    handler._send_json = _send_json
    return handler


def call_session_mode(handler, body: dict) -> None:
    """Drive do_POST for /api/session/mode with the given body dict."""
    handler.path = "/api/session/mode"
    handler.command = "POST"

    # Patch _read_json_body (the actual method used in do_POST) to return
    # our test body dict without needing a real socket/rfile.
    captured_body = body

    def patched_read_json_body(self_h):
        return captured_body

    with patch.object(AdminGuiHandler, "_read_json_body", patched_read_json_body):
        AdminGuiHandler.do_POST(handler)


# ---------------------------------------------------------------------------
# 1. Source-level check: no 'or "default"' pattern for session_id
# ---------------------------------------------------------------------------

class TestNoFalsyOrPattern(unittest.TestCase):

    def _get_session_mode_block(self) -> str:
        """Extract the /api/session/mode handler block from do_POST source.

        Finds the LAST occurrence of '"/api/session/mode"' to skip any
        earlier reference blocks and land on the implementation block.
        """
        src = inspect.getsource(AdminGuiHandler.do_POST)
        marker = '"/api/session/mode"'
        idx = src.rfind(marker)  # use rfind to get last occurrence
        if idx == -1:
            return src  # fallback: search entire source
        # Return ~600 chars after the marker to capture the full block.
        return src[idx: idx + 600]

    def test_no_or_default_for_session_id(self):
        """session_id must NOT use 'or "default"' — use is-None check instead."""
        block = self._get_session_mode_block()
        # The old anti-pattern: body.get("session_id") or "default"
        self.assertNotIn(
            'body.get("session_id") or "default"',
            block,
            "session_id still uses 'or \"default\"' falsy substitution",
        )

    def test_is_none_check_present(self):
        """session_id extraction must use an explicit is None check."""
        block = self._get_session_mode_block()
        self.assertIn(
            "is not None",
            block,
            "session_id does not use 'is not None' guard",
        )

    def test_session_id_clamped(self):
        """session_id should be clamped to prevent unbounded growth."""
        block = self._get_session_mode_block()
        self.assertIn(
            "[:128]",
            block,
            "session_id is not clamped after extraction",
        )


# ---------------------------------------------------------------------------
# 2. Functional: integer 0 is NOT silently mapped to "default"
# ---------------------------------------------------------------------------

class TestFalsySessionIdBehaviour(unittest.TestCase):

    def test_integer_zero_not_mapped_to_default(self):
        """session_id=0 must pass '0' to session_set_mode, not 'default'."""
        srv = MagicMock()
        srv.session_set_mode.return_value = {"ok": True}
        handler = make_handler(srv)
        call_session_mode(handler, {"session_id": 0, "mode": "normal"})
        self.assertTrue(srv.session_set_mode.called)
        actual_sid = srv.session_set_mode.call_args[0][0]
        self.assertNotEqual(actual_sid, "default", "session_id=0 was silently mapped to 'default'")
        self.assertEqual(actual_sid, "0")

    def test_none_session_id_maps_to_default(self):
        """Missing session_id (None) SHOULD use 'default'."""
        srv = MagicMock()
        srv.session_set_mode.return_value = {"ok": True}
        handler = make_handler(srv)
        call_session_mode(handler, {"mode": "normal"})  # no session_id key
        actual_sid = srv.session_set_mode.call_args[0][0]
        self.assertEqual(actual_sid, "default")

    def test_explicit_none_session_id_maps_to_default(self):
        """session_id=null (JSON null → Python None) SHOULD use 'default'."""
        srv = MagicMock()
        srv.session_set_mode.return_value = {"ok": True}
        handler = make_handler(srv)
        call_session_mode(handler, {"session_id": None, "mode": "normal"})
        actual_sid = srv.session_set_mode.call_args[0][0]
        self.assertEqual(actual_sid, "default")

    def test_string_session_id_preserved(self):
        """A normal string session_id is passed through unchanged."""
        srv = MagicMock()
        srv.session_set_mode.return_value = {"ok": True}
        handler = make_handler(srv)
        call_session_mode(handler, {"session_id": "my-session", "mode": "normal"})
        actual_sid = srv.session_set_mode.call_args[0][0]
        self.assertEqual(actual_sid, "my-session")

    def test_session_id_clamped_to_128(self):
        """session_id longer than 128 chars is truncated."""
        srv = MagicMock()
        srv.session_set_mode.return_value = {"ok": True}
        handler = make_handler(srv)
        long_sid = "a" * 300
        call_session_mode(handler, {"session_id": long_sid, "mode": "normal"})
        actual_sid = srv.session_set_mode.call_args[0][0]
        self.assertLessEqual(len(actual_sid), 128)

    def test_invalid_composite_top_n_returns_400(self):
        """composite_top_n with non-integer value returns 400."""
        srv = MagicMock()
        srv.session_set_mode.return_value = {"ok": True}
        handler = make_handler(srv)
        call_session_mode(handler, {"session_id": "s1", "mode": "normal", "composite_top_n": "bad"})
        codes = [code for code, _ in handler._responses]
        self.assertIn(400, codes)

    def test_valid_composite_top_n_passes_through(self):
        """composite_top_n as an integer is forwarded to session_set_mode."""
        srv = MagicMock()
        srv.session_set_mode.return_value = {"ok": True}
        handler = make_handler(srv)
        call_session_mode(handler, {"session_id": "s1", "mode": "normal", "composite_top_n": 5})
        actual_n = srv.session_set_mode.call_args[0][2]
        self.assertEqual(actual_n, 5)


if __name__ == "__main__":
    unittest.main()
