#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_toolproxy_native_probe.py
Zone: release/package
Purpose: Validate the canonical ToolProxy native JSON-over-UDS diagnostic probe.
Inputs: Workspace source files and mocked Unix socket transport.
Outputs: unittest assertions only.
Side effects: None.
Tests: direct unittest execution.
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import importlib
import os
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

import noemaforge_toolproxy_diag as diag


class FakeUnixSocket:
    instances: list["FakeUnixSocket"] = []

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.timeout: float | None = None
        self.connected_to: str | None = None
        self.sent = b""
        self.shutdown_how: int | None = None
        self.closed = False
        self._responses = [b'{"ok": false, "error": "denied"}', b""]
        FakeUnixSocket.instances.append(self)

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def connect(self, path: str) -> None:
        self.connected_to = path

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def shutdown(self, how: int) -> None:
        self.shutdown_how = how

    def recv(self, _size: int) -> bytes:
        return self._responses.pop(0)

    def close(self) -> None:
        self.closed = True


class ToolProxyNativeProbeTests(unittest.TestCase):
    def test_default_socket_fallback_resolves_platform_path_property(self) -> None:
        self.assertNotIn("bound method", diag.DEFAULT_SOCKET)
        self.assertNotIn("toolproxy_socket", diag.DEFAULT_SOCKET)
        self.assertEqual(str(diag._pp.toolproxy_socket), diag.DEFAULT_SOCKET)

    def test_default_socket_helper_accepts_legacy_method_shape(self) -> None:
        class LegacyPaths:
            def toolproxy_socket(self) -> str:
                return "/tmp/legacy-toolproxy.sock"

        self.assertEqual("/tmp/legacy-toolproxy.sock", diag._toolproxy_socket_default(LegacyPaths()))

    def test_default_socket_keeps_environment_override(self) -> None:
        global diag
        with patch.dict(os.environ, {"NOEMAFORGE_TOOLPROXY_SOCKET": "/tmp/env-toolproxy.sock"}):
            diag = importlib.reload(diag)
            self.assertEqual("/tmp/env-toolproxy.sock", diag.DEFAULT_SOCKET)
        diag = importlib.reload(diag)

    def test_probe_uses_native_json_envelope_and_half_closes_write_side(self) -> None:
        FakeUnixSocket.instances = []
        with patch("noemaforge_toolproxy_diag.socket.socket", side_effect=FakeUnixSocket):
            report = diag.probe_toolproxy("/tmp/noemaforge-toolproxy.sock", timeout=2.5)

        self.assertTrue(report["ok"], report)
        self.assertEqual("native_json_over_unix_socket", report["probe"])
        fake = FakeUnixSocket.instances[0]
        self.assertEqual("/tmp/noemaforge-toolproxy.sock", fake.connected_to)
        self.assertEqual(2.5, fake.timeout)
        self.assertEqual(socket.SHUT_WR, fake.shutdown_how)
        self.assertTrue(fake.closed)
        payload = json.loads(fake.sent.decode("utf-8"))
        self.assertEqual("operator.status", payload["action"])
        self.assertEqual("toolproxy-probe.invalid", payload["token"])
        self.assertEqual("dev.work", payload["meta"]["stream_id"])

    def test_compat_helper_delegates_to_canonical_cli_without_raw_curl_probe(self) -> None:
        helper = PROJECT_ROOT / "helpers" / "noemaforge-toolproxy-diag"
        text = helper.read_text(encoding="utf-8")

        self.assertIn("exec /usr/local/sbin/noemaforge toolproxy diag", text)
        self.assertNotIn("curl", text)
        self.assertNotIn("--unix-socket", text)
        self.assertNotIn("/health", text)


if __name__ == "__main__":
    unittest.main()
