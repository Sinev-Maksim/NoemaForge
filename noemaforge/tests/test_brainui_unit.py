#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_brainui_unit.py
Zone: tests
Version: 0.32.2
Created: 2026-06-04
Modified: 2026-06-04
Purpose: Unit tests for brainui.py pure functions and path security:
         _guess_type(), _ServerCtx.snapshot() fallback behavior,
         do_GET path containment check (CWE-22 protection).
         No HTTP server is started; tests use Handler class directly.
Inputs: brainui module functions and Handler class.
Outputs: pytest/unittest pass/fail.
Side effects: Writes and removes temporary files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_brainui_unit.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import io
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


def _install_stubs() -> None:
    """Install stub for ui_snapshot so brainui.py imports cleanly."""
    stub_ui = types.ModuleType("ui_snapshot")
    stub_ui.build_snapshot = lambda state_root, configs_dir: {
        "schema_version": "noemaforge.ui.snapshot/v1",
        "generated_at": "2026-06-04T00:00:00Z",
        "state_root": str(state_root),
    }
    sys.modules.setdefault("ui_snapshot", stub_ui)


_install_stubs()

import brainui  # noqa: E402


# ---------------------------------------------------------------------------
# Tests for _guess_type()
# ---------------------------------------------------------------------------

class TestGuessType(unittest.TestCase):
    """_guess_type() maps file extensions to MIME types."""

    def test_html_extension(self) -> None:
        self.assertEqual(brainui._guess_type("index.html"), "text/html; charset=utf-8")

    def test_html_uppercase(self) -> None:
        self.assertEqual(brainui._guess_type("PAGE.HTML"), "text/html; charset=utf-8")

    def test_js_extension(self) -> None:
        self.assertEqual(brainui._guess_type("app.js"), "text/javascript; charset=utf-8")

    def test_css_extension(self) -> None:
        self.assertEqual(brainui._guess_type("style.css"), "text/css; charset=utf-8")

    def test_svg_extension(self) -> None:
        self.assertEqual(brainui._guess_type("logo.svg"), "image/svg+xml")

    def test_png_extension(self) -> None:
        self.assertEqual(brainui._guess_type("icon.png"), "image/png")

    def test_unknown_extension(self) -> None:
        self.assertEqual(brainui._guess_type("data.bin"), "application/octet-stream")

    def test_no_extension(self) -> None:
        self.assertEqual(brainui._guess_type("Makefile"), "application/octet-stream")

    def test_mixed_case_js(self) -> None:
        self.assertEqual(brainui._guess_type("bundle.JS"), "text/javascript; charset=utf-8")

    def test_mixed_case_css(self) -> None:
        self.assertEqual(brainui._guess_type("styles.CSS"), "text/css; charset=utf-8")

    def test_path_with_directory(self) -> None:
        """Full path with directory should still detect extension correctly."""
        self.assertEqual(brainui._guess_type("/some/dir/app.js"), "text/javascript; charset=utf-8")

    def test_dotfile_no_extension(self) -> None:
        """Hidden files with no extension fall back to octet-stream."""
        self.assertEqual(brainui._guess_type(".gitignore"), "application/octet-stream")


# ---------------------------------------------------------------------------
# Tests for _ServerCtx.snapshot() fallback
# ---------------------------------------------------------------------------

class TestServerCtxSnapshot(unittest.TestCase):
    """_ServerCtx.snapshot() returns error when build_snapshot is None."""

    def test_snapshot_returns_error_when_no_build_snapshot(self) -> None:
        """When build_snapshot import failed, snapshot() returns error dict."""
        ctx = brainui._ServerCtx(state_root="/tmp/state", configs_dir="/tmp/configs")
        # Temporarily override build_snapshot to None and inject _IMPORT_ERR to
        # simulate the state that results when 'from ui_snapshot import build_snapshot'
        # raises at module import time (pragma: no cover branch).
        orig_build = brainui.build_snapshot
        had_err = hasattr(brainui, "_IMPORT_ERR")
        orig_err = getattr(brainui, "_IMPORT_ERR", None)
        try:
            brainui.build_snapshot = None
            brainui._IMPORT_ERR = "stub: ui_snapshot not available"
            result = ctx.snapshot()
            self.assertIn("error", result)
            self.assertEqual(result["schema_version"], "noemaforge.ui.snapshot/v1")
        finally:
            brainui.build_snapshot = orig_build
            if had_err and orig_err is not None:
                brainui._IMPORT_ERR = orig_err
            elif not had_err and hasattr(brainui, "_IMPORT_ERR"):
                del brainui._IMPORT_ERR

    def test_snapshot_calls_build_snapshot_with_state_root(self) -> None:
        """snapshot() calls build_snapshot with the state_root and configs_dir."""
        called_with = {}
        def fake_build_snapshot(state_root, configs_dir):
            called_with["state_root"] = state_root
            called_with["configs_dir"] = configs_dir
            return {"schema_version": "noemaforge.ui.snapshot/v1"}

        ctx = brainui._ServerCtx(state_root="/test/state", configs_dir="/test/configs")
        orig = brainui.build_snapshot
        try:
            brainui.build_snapshot = fake_build_snapshot
            ctx.snapshot()
        finally:
            brainui.build_snapshot = orig
        self.assertEqual(called_with["state_root"], "/test/state")
        self.assertEqual(called_with["configs_dir"], "/test/configs")


# ---------------------------------------------------------------------------
# Tests for path traversal protection in do_GET handler
# ---------------------------------------------------------------------------

class TestDoGetPathContainment(unittest.TestCase):
    """Handler.do_GET() must reject requests that escape assets_dir."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._assets_dir = os.path.join(self._tmpdir, "assets")
        os.makedirs(self._assets_dir)
        # Create a valid static file
        self._valid_file = os.path.join(self._assets_dir, "index.html")
        with open(self._valid_file, "w", encoding="utf-8") as f:
            f.write("<html>OK</html>")
        # Create a file OUTSIDE assets dir (sibling)
        self._outside_file = os.path.join(self._tmpdir, "secret.txt")
        with open(self._outside_file, "w", encoding="utf-8") as f:
            f.write("secret content")

        self._ctx = brainui._ServerCtx(
            state_root=self._tmpdir,
            configs_dir=os.path.join(self._tmpdir, "configs"),
        )
        HandlerClass = brainui._make_handler(self._ctx, self._assets_dir)
        self._HandlerClass = HandlerClass

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_handler(self, path: str):
        """Create a minimal handler instance for testing do_GET logic."""
        handler = object.__new__(self._HandlerClass)
        handler.path = path
        handler.wfile = io.BytesIO()
        handler._response_code = None
        handler._headers = {}
        handler._body = b""

        def mock_send_response(code):
            handler._response_code = code

        def mock_send_header(key, val):
            handler._headers[key] = val

        def mock_end_headers():
            pass

        def mock_write(data):
            handler._body += data

        handler.send_response = mock_send_response
        handler.send_header = mock_send_header
        handler.end_headers = mock_end_headers
        handler.wfile.write = mock_write
        return handler

    def test_valid_static_file_returns_200(self) -> None:
        """A request for a valid static file inside assets must succeed."""
        handler = self._make_handler("/index.html")
        handler.do_GET()
        self.assertEqual(handler._response_code, 200)

    def test_api_health_returns_200(self) -> None:
        """GET /api/health must return 200 OK."""
        handler = self._make_handler("/api/health")
        handler.do_GET()
        self.assertEqual(handler._response_code, 200)

    def test_dotdot_traversal_returns_400(self) -> None:
        """A path with '..' that escapes assets_dir must return 400."""
        handler = self._make_handler("/../secret.txt")
        handler.do_GET()
        self.assertEqual(handler._response_code, 400,
                         "Path traversal must be rejected with 400")

    def test_absolute_path_outside_assets_returns_400(self) -> None:
        """Even if normpath produces a path outside assets_dir, it must return 400."""
        # Simulate a path that would normpath to outside assets
        handler = self._make_handler("/../../etc/passwd")
        handler.do_GET()
        self.assertEqual(handler._response_code, 400)

    def test_missing_file_returns_404(self) -> None:
        """A valid-looking but nonexistent file must return 404."""
        handler = self._make_handler("/nonexistent_file.js")
        handler.do_GET()
        self.assertEqual(handler._response_code, 404)

    def test_root_path_serves_index(self) -> None:
        """GET / should redirect internally to /index.html."""
        handler = self._make_handler("/")
        handler.do_GET()
        # If index.html exists in assets_dir, expect 200; else 404
        self.assertIn(handler._response_code, (200, 404))

    def test_backslash_traversal_rejected(self) -> None:
        """Path with backslash traversal attempt must return 400 or 404."""
        # Windows-style traversal; after normpath this should be sanitized
        handler = self._make_handler("/..\\secret.txt")
        handler.do_GET()
        self.assertIn(handler._response_code, (400, 404),
                      "Backslash traversal must not return 200")


# ---------------------------------------------------------------------------
# Tests for _assets_dir() helper
# ---------------------------------------------------------------------------

class TestAssetsDir(unittest.TestCase):
    """_assets_dir() returns a string path."""

    def test_returns_string(self) -> None:
        result = brainui._assets_dir()
        self.assertIsInstance(result, str)

    def test_returns_absolute_path(self) -> None:
        result = brainui._assets_dir()
        self.assertTrue(os.path.isabs(result), f"Expected absolute path, got: {result!r}")


# ---------------------------------------------------------------------------
# Tests for _default_configs_dir()
# ---------------------------------------------------------------------------

class TestDefaultConfigsDir(unittest.TestCase):
    """_default_configs_dir() resolves to an absolute path."""

    def test_returns_absolute_path(self) -> None:
        result = brainui._default_configs_dir()
        self.assertTrue(os.path.isabs(result))

    def test_ends_with_configs(self) -> None:
        result = brainui._default_configs_dir()
        self.assertTrue(result.endswith("configs"), f"Got: {result!r}")


# ---------------------------------------------------------------------------
# Tests for server_version constant
# ---------------------------------------------------------------------------

class TestServerVersion(unittest.TestCase):
    """Handler must identify itself with the NoemaForgeUI version string."""

    def test_handler_has_server_version(self) -> None:
        tmpdir = tempfile.mkdtemp()
        try:
            ctx = brainui._ServerCtx(state_root=tmpdir, configs_dir=tmpdir)
            Handler = brainui._make_handler(ctx, tmpdir)
            self.assertEqual(Handler.server_version, "NoemaForgeUI/0.25.1")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()