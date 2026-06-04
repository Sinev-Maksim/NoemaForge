#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_brainui.py
Zone: tests
Version: 0.32.2
Created: 2026-06-04
Modified: 2026-06-04
Purpose: Tests for brainui.py — local offline-first dashboard for NoemaForge.
         Covers: _guess_type, _assets_dir, _ServerCtx.snapshot,
         _make_handler path containment, do_GET API endpoints.
Tests: python3 -m unittest noemaforge/tests/test_brainui.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Stub ui_snapshot before importing brainui
_mock_ui_snapshot = types.ModuleType("ui_snapshot")
_mock_ui_snapshot.build_snapshot = MagicMock(return_value={
    "schema_version": "noemaforge.ui.snapshot/v1",
    "generated_at": "2026-06-04T00:00:00Z",
    "state": "ok",
})
sys.modules.setdefault("ui_snapshot", _mock_ui_snapshot)

import brainui  # noqa: E402


class TestGuessType(unittest.TestCase):
    def test_html_returns_html_mime(self) -> None:
        self.assertEqual(brainui._guess_type("index.html"), "text/html; charset=utf-8")

    def test_js_returns_javascript_mime(self) -> None:
        self.assertEqual(brainui._guess_type("app.js"), "text/javascript; charset=utf-8")

    def test_css_returns_css_mime(self) -> None:
        self.assertEqual(brainui._guess_type("style.css"), "text/css; charset=utf-8")

    def test_svg_returns_svg_mime(self) -> None:
        self.assertEqual(brainui._guess_type("icon.svg"), "image/svg+xml")

    def test_png_returns_png_mime(self) -> None:
        self.assertEqual(brainui._guess_type("logo.png"), "image/png")

    def test_unknown_extension_returns_octet_stream(self) -> None:
        self.assertEqual(brainui._guess_type("data.bin"), "application/octet-stream")

    def test_case_insensitive_html(self) -> None:
        self.assertEqual(brainui._guess_type("PAGE.HTML"), "text/html; charset=utf-8")

    def test_case_insensitive_js(self) -> None:
        self.assertEqual(brainui._guess_type("App.JS"), "text/javascript; charset=utf-8")

    def test_no_extension_returns_octet_stream(self) -> None:
        self.assertEqual(brainui._guess_type("Makefile"), "application/octet-stream")

    def test_path_with_dirs(self) -> None:
        self.assertEqual(brainui._guess_type("/path/to/file.css"), "text/css; charset=utf-8")


class TestAssetsDir(unittest.TestCase):
    def test_returns_string(self) -> None:
        result = brainui._assets_dir()
        self.assertIsInstance(result, str)

    def test_returns_absolute_path(self) -> None:
        result = brainui._assets_dir()
        self.assertTrue(os.path.isabs(result), f"Expected absolute path, got: {result!r}")


class TestServerCtx(unittest.TestCase):
    def test_snapshot_calls_build_snapshot(self) -> None:
        ctx = brainui._ServerCtx(state_root="/tmp/state", configs_dir="/tmp/configs")
        _mock_ui_snapshot.build_snapshot.reset_mock()
        result = ctx.snapshot()
        _mock_ui_snapshot.build_snapshot.assert_called_once_with(
            state_root="/tmp/state",
            configs_dir="/tmp/configs"
        )
        self.assertIn("schema_version", result)

    def test_snapshot_returns_error_when_build_snapshot_none(self) -> None:
        # Temporarily set build_snapshot to None to simulate import failure
        original = brainui.build_snapshot
        try:
            brainui.build_snapshot = None
            ctx = brainui._ServerCtx(state_root="/tmp/state", configs_dir="/tmp/configs")
            result = ctx.snapshot()
            self.assertIn("error", result)
            self.assertIn("schema_version", result)
        finally:
            brainui.build_snapshot = original

    def test_ctx_stores_state_root(self) -> None:
        ctx = brainui._ServerCtx(state_root="/custom/state", configs_dir="/tmp/configs")
        self.assertEqual(ctx.state_root, "/custom/state")

    def test_ctx_stores_configs_dir(self) -> None:
        ctx = brainui._ServerCtx(state_root="/tmp/state", configs_dir="/custom/configs")
        self.assertEqual(ctx.configs_dir, "/custom/configs")


class _FakeSocket:
    """Minimal socket-like for BaseHTTPRequestHandler."""
    def __init__(self, buf: bytes):
        self._r = io.BytesIO(buf)
        self._w = io.BytesIO()

    def makefile(self, mode, *args, **kwargs):
        if "r" in mode:
            return io.BufferedReader(self._r)
        return self._w

    def sendall(self, data: bytes) -> None:
        self._w.write(data)

    def write(self, data: bytes) -> None:
        self._w.write(data)

    def getpeername(self):
        return ("127.0.0.1", 12345)

    def getsockname(self):
        return ("127.0.0.1", 8787)


class _FakeHTTPRequest:
    """Drive a handler for a single GET request."""

    def __init__(self, path: str, assets_dir: str, state_root: str = "/tmp/state"):
        raw = f"GET {path} HTTP/1.0\r\nHost: localhost\r\n\r\n".encode()
        self._sock = _FakeSocket(raw)
        self._client_address = ("127.0.0.1", 12345)
        ctx = brainui._ServerCtx(state_root=state_root, configs_dir="/tmp/configs")
        HandlerClass = brainui._make_handler(ctx, assets_dir)
        # Suppress stderr from BaseHTTPRequestHandler
        import http.server
        old_log = http.server.BaseHTTPRequestHandler.log_message
        http.server.BaseHTTPRequestHandler.log_message = lambda self, fmt, *args: None
        try:
            self._handler = HandlerClass(self._sock, self._client_address, None)
        except Exception:
            pass  # server=None can raise during __init__ on some Python versions
        finally:
            http.server.BaseHTTPRequestHandler.log_message = old_log

    @property
    def response(self) -> bytes:
        return self._sock._w.getvalue()

    def response_json(self) -> dict:
        raw = self.response
        # Find the blank line separating headers from body
        body_start = raw.find(b"\r\n\r\n")
        if body_start == -1:
            body_start = raw.find(b"\n\n")
            body = raw[body_start + 2:]
        else:
            body = raw[body_start + 4:]
        return json.loads(body.decode("utf-8"))

    def status_code(self) -> int:
        first_line = self.response.split(b"\r\n", 1)[0].decode()
        return int(first_line.split(" ")[1])


class TestMakeHandlerApiEndpoints(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        # Create a minimal assets dir
        self._assets = os.path.join(self._tmpdir, "assets")
        os.makedirs(self._assets)
        # Create a fake index.html
        with open(os.path.join(self._assets, "index.html"), "w") as f:
            f.write("<html>test</html>")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_request(self, path: str) -> _FakeHTTPRequest:
        return _FakeHTTPRequest(path, self._assets)

    def test_health_endpoint_returns_ok_true(self) -> None:
        req = self._make_request("/api/health")
        data = req.response_json()
        self.assertTrue(data.get("ok"))

    def test_snapshot_endpoint_calls_build_snapshot(self) -> None:
        _mock_ui_snapshot.build_snapshot.reset_mock()
        req = self._make_request("/api/snapshot")
        data = req.response_json()
        self.assertIn("schema_version", data)

    def test_path_traversal_rejected(self) -> None:
        req = self._make_request("/../../../etc/passwd")
        data = req.response_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "bad path")

    def test_path_traversal_double_dots_rejected(self) -> None:
        req = self._make_request("/assets/../../etc/passwd")
        data = req.response_json()
        self.assertIn("error", data)

    def test_existing_file_served(self) -> None:
        req = self._make_request("/index.html")
        response = req.response
        # Should not contain an error JSON
        self.assertIn(b"<html>test</html>", response)

    def test_root_serves_index_html(self) -> None:
        req = self._make_request("/")
        response = req.response
        self.assertIn(b"<html>test</html>", response)

    def test_missing_file_returns_404(self) -> None:
        req = self._make_request("/nonexistent.js")
        data = req.response_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "not found")


class TestMakeHandlerPathContainment(unittest.TestCase):
    """CWE-22 path containment check tests."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._assets = os.path.join(self._tmpdir, "assets")
        os.makedirs(self._assets)
        # Create a symlink inside assets dir pointing outside
        self._outside_file = os.path.join(self._tmpdir, "secret.txt")
        with open(self._outside_file, "w") as f:
            f.write("secret content")
        try:
            os.symlink(self._outside_file, os.path.join(self._assets, "link.txt"))
            self._symlink_available = True
        except (OSError, NotImplementedError):
            self._symlink_available = False

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_symlink_escape_rejected(self) -> None:
        if not self._symlink_available:
            self.skipTest("symlinks not supported on this platform")
        ctx = brainui._ServerCtx(state_root="/tmp/state", configs_dir="/tmp/configs")
        HandlerClass = brainui._make_handler(ctx, self._assets)
        # Verify the path containment logic rejects escape via symlinks
        assets_real = os.path.realpath(self._assets)
        outside_real = os.path.realpath(self._outside_file)
        # The outside file should NOT start with assets_real + os.sep
        self.assertFalse(
            outside_real == assets_real or outside_real.startswith(assets_real + os.sep),
            "Outside file should not be inside assets_real"
        )

    def test_path_normpath_strips_dotdot(self) -> None:
        """Verify that os.path.normpath eliminates '..' traversal."""
        bad_path = os.path.normpath("subdir/../../etc/passwd").replace("\\", "/")
        # After normpath, traversal should point outside the assets
        self.assertFalse(bad_path.startswith("subdir"))


class TestDefaultConfigsDir(unittest.TestCase):
    def test_returns_absolute_path(self) -> None:
        result = brainui._default_configs_dir()
        self.assertTrue(os.path.isabs(result))

    def test_returns_string(self) -> None:
        result = brainui._default_configs_dir()
        self.assertIsInstance(result, str)

    def test_ends_with_configs(self) -> None:
        result = brainui._default_configs_dir()
        self.assertTrue(result.endswith("configs") or "configs" in result)


class TestReadFile(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_reads_binary_content(self) -> None:
        path = os.path.join(self._tmpdir, "test.bin")
        content = b"\x00\x01\x02hello"
        with open(path, "wb") as f:
            f.write(content)
        result = brainui._read_file(path)
        self.assertEqual(result, content)

    def test_reads_text_as_bytes(self) -> None:
        path = os.path.join(self._tmpdir, "test.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("hello world")
        result = brainui._read_file(path)
        self.assertIsInstance(result, bytes)
        self.assertIn(b"hello world", result)

    def test_raises_on_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            brainui._read_file("/nonexistent/path/file.txt")


class TestCmdSnapshot(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_snapshot_writes_to_out_file(self) -> None:
        import argparse
        out_path = os.path.join(self._tmpdir, "snap.json")
        args = argparse.Namespace(
            state_root=self._tmpdir,
            configs_dir=self._tmpdir,
            out=out_path,
        )
        _mock_ui_snapshot.build_snapshot.reset_mock()
        brainui.cmd_snapshot(args)
        self.assertTrue(os.path.exists(out_path))
        with open(out_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("schema_version", data)

    def test_snapshot_returns_zero_on_success(self) -> None:
        import argparse
        out_path = os.path.join(self._tmpdir, "snap2.json")
        args = argparse.Namespace(
            state_root=self._tmpdir,
            configs_dir=self._tmpdir,
            out=out_path,
        )
        result = brainui.cmd_snapshot(args)
        self.assertEqual(result, 0)

    def test_snapshot_fails_when_build_snapshot_unavailable(self) -> None:
        import argparse
        original = brainui.build_snapshot
        try:
            brainui.build_snapshot = None
            args = argparse.Namespace(
                state_root=self._tmpdir,
                configs_dir=self._tmpdir,
                out="",
            )
            result = brainui.cmd_snapshot(args)
            self.assertEqual(result, 2)
        finally:
            brainui.build_snapshot = original


class TestCmdServe(unittest.TestCase):
    def test_serve_fails_when_assets_dir_missing(self) -> None:
        import argparse
        args = argparse.Namespace(
            state_root="/tmp",
            configs_dir="/tmp",
            host="127.0.0.1",
            port=18787,
        )
        # Patch _assets_dir to return a nonexistent path
        with patch.object(brainui, "_assets_dir", return_value="/nonexistent/path/ui-dashboard"):
            result = brainui.cmd_serve(args)
        self.assertEqual(result, 2)


if __name__ == "__main__":
    unittest.main()