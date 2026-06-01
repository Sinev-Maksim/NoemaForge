#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_serve_static.py
Zone: tests
Version: 0.32.2
Created: 2026-05-31
Modified: 2026-05-31
Purpose: Cover AdminGuiHandler._serve_static() — the static-asset dispatch
         path.  Previously had zero test coverage.  Tests verify:
           - api/ prefix → 404 JSON (not routed to filesystem)
           - ui/ path traversal → 404 (parent-containment guard enforced)
           - ui/ non-existent file → 404
           - ui/ directory path → 404
           - ui/ valid file → served with correct bytes
           - general path traversal → silent fallback to index.html
           - general non-existent path → fallback to index.html
           - empty/root path → serves index.html
           - URL-encoded traversal → fallback to index.html
           - content-type detection for CSS files
Inputs: AdminGuiHandler from admin_gui_server.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_serve_static.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path


def _install_stubs() -> None:
    stub_ver = types.ModuleType("noemaforge_version")
    stub_ver.RUNTIME_VERSION = "0.32.2"
    sys.modules.setdefault("noemaforge_version", stub_ver)

    stub_orch = types.ModuleType("orchestration_state")
    stub_orch.nowz = lambda: "2026-05-31T00:00:00Z"
    stub_orch.normalize_session_record = lambda r: r
    stub_orch.is_active_job = lambda job: False
    sys.modules.setdefault("orchestration_state", stub_orch)

    stub_prod = types.ModuleType("production_ai_contracts")
    sys.modules.setdefault("production_ai_contracts", stub_prod)

    stub_priv = types.ModuleType("privileged_gui_job_runner")
    stub_priv.enrich_privileged_job = lambda job, **_kw: job
    sys.modules.setdefault("privileged_gui_job_runner", stub_priv)


_install_stubs()

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from admin_gui_server import AdminGuiHandler  # noqa: E402


# ---------------------------------------------------------------------------
# Infrastructure: minimal stub so _serve_static() can be called without a
# real socket / HTTP connection.
# ---------------------------------------------------------------------------

class _StubServer:
    """Minimal server shim providing root and ui_dir to AdminGuiHandler."""

    def __init__(self, root: Path, ui_dir: Path) -> None:
        self.root = root
        self.ui_dir = ui_dir


class _StubHandler(AdminGuiHandler):
    """AdminGuiHandler subclass that captures _send_json / _send_bytes calls."""

    def __init__(self, root: Path, ui_dir: Path) -> None:
        # Do NOT call BaseHTTPRequestHandler.__init__ — it needs a real socket.
        self.server = _StubServer(root, ui_dir)
        self._json_obj: object = None
        self._json_status: int | None = None
        self._bytes_data: bytes | None = None
        self._bytes_type: str | None = None
        self._bytes_status: int | None = None

    def _send_json(self, obj: object, status: int = 200) -> None:  # type: ignore[override]
        self._json_obj = obj
        self._json_status = status

    def _send_bytes(  # type: ignore[override]
        self,
        data: bytes,
        content_type: str = "application/octet-stream",
        status: int = 200,
        *,
        head_only: bool = False,
    ) -> None:
        self._bytes_data = data
        self._bytes_type = content_type
        self._bytes_status = status


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestServeStatic(unittest.TestCase):
    """AdminGuiHandler._serve_static() — routing, traversal guards, fallbacks."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.root_dir = Path(self._tmpdir) / "root"
        self.ui_dir = Path(self._tmpdir) / "ui"
        self.root_dir.mkdir()
        self.ui_dir.mkdir()
        # index.html required for general-path fallback tests
        (self.ui_dir / "index.html").write_bytes(b"<html>index</html>")
        # A CSS asset in ui_dir for content-type and general-path tests
        (self.ui_dir / "style.css").write_bytes(b"body{margin:0}")
        # A file inside root/ui/ for the ui/ prefix tests
        (self.root_dir / "ui").mkdir()
        (self.root_dir / "ui" / "icon.png").write_bytes(b"\x89PNG")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_handler(self) -> _StubHandler:
        return _StubHandler(self.root_dir, self.ui_dir)

    # ------------------------------------------------------------------
    # api/ prefix — must never touch the filesystem
    # ------------------------------------------------------------------

    def test_api_prefix_returns_404(self) -> None:
        """Paths starting with api/ must return 404 without filesystem access."""
        h = self._make_handler()
        h._serve_static("/api/health")
        self.assertEqual(h._json_status, 404)
        self.assertIsNone(h._bytes_data, "Filesystem read must not occur for api/ paths")

    def test_api_prefix_json_body_is_error(self) -> None:
        """api/ 404 response must be a JSON error object."""
        h = self._make_handler()
        h._serve_static("/api/events?after_index=0")
        self.assertIsInstance(h._json_obj, dict)
        self.assertFalse(h._json_obj.get("ok"))  # type: ignore[union-attr]

    # ------------------------------------------------------------------
    # ui/ prefix — parent-containment traversal guard
    # ------------------------------------------------------------------

    def test_ui_path_traversal_returns_404(self) -> None:
        """ui/../../etc/passwd must not escape root: returns 404, no bytes."""
        h = self._make_handler()
        h._serve_static("/ui/../../etc/passwd")
        self.assertEqual(h._json_status, 404)
        self.assertIsNone(h._bytes_data, "Traversal outside root must not be served")

    def test_ui_traversal_json_body_identifies_path(self) -> None:
        """ui/ traversal 404 response must carry the rel path for debugging."""
        h = self._make_handler()
        h._serve_static("/ui/../../etc/passwd")
        body = h._json_obj  # type: ignore[union-attr]
        self.assertIn("path", body)  # type: ignore[operator]

    def test_ui_nonexistent_file_returns_404(self) -> None:
        """ui/ path referencing a non-existent file must return 404."""
        h = self._make_handler()
        h._serve_static("/ui/missing.png")
        self.assertEqual(h._json_status, 404)

    def test_ui_directory_path_returns_404(self) -> None:
        """ui/ path resolving to a directory (not a file) must return 404."""
        h = self._make_handler()
        # root/ui/ is a directory — should reject
        h._serve_static("/ui/")
        self.assertEqual(h._json_status, 404)

    def test_ui_valid_file_served(self) -> None:
        """ui/ path for an existing file within root must be served."""
        h = self._make_handler()
        h._serve_static("/ui/icon.png")
        self.assertIsNone(h._json_obj, "No JSON error should be sent for a valid ui/ asset")
        self.assertEqual(h._bytes_data, b"\x89PNG")

    # ------------------------------------------------------------------
    # General path — ui_dir containment + fallback to index.html
    # ------------------------------------------------------------------

    def test_general_existing_file_served(self) -> None:
        """A file that exists in ui_dir must be served directly."""
        h = self._make_handler()
        h._serve_static("/style.css")
        self.assertEqual(h._bytes_data, b"body{margin:0}")
        self.assertIsNone(h._json_obj)

    def test_general_nonexistent_falls_back_to_index(self) -> None:
        """A path that doesn't exist in ui_dir must fall back to index.html."""
        h = self._make_handler()
        h._serve_static("/nonexistent.js")
        self.assertEqual(h._bytes_data, b"<html>index</html>",
                         "Non-existent general path must fall back to index.html")

    def test_general_traversal_falls_back_to_index(self) -> None:
        """Traversal outside ui_dir must fall back to index.html, not crash."""
        h = self._make_handler()
        h._serve_static("/../../etc/passwd")
        # Must not raise; must not serve passwd (index.html is the fallback)
        self.assertEqual(h._bytes_data, b"<html>index</html>",
                         "Traversal outside ui_dir must serve index.html as fallback")

    def test_url_encoded_traversal_falls_back_to_index(self) -> None:
        """URL-encoded traversal (%2e%2e) resolves outside ui_dir → index.html."""
        h = self._make_handler()
        h._serve_static("/%2e%2e/etc/passwd")
        self.assertEqual(h._bytes_data, b"<html>index</html>")

    def test_empty_path_serves_index(self) -> None:
        """Root path / defaults to index.html (SPA entrypoint)."""
        h = self._make_handler()
        h._serve_static("/")
        self.assertEqual(h._bytes_data, b"<html>index</html>")

    # ------------------------------------------------------------------
    # Content-type detection
    # ------------------------------------------------------------------

    def test_css_content_type(self) -> None:
        """CSS files must be served with a text/css content-type header."""
        h = self._make_handler()
        h._serve_static("/style.css")
        self.assertIsNotNone(h._bytes_type)
        self.assertIn("css", h._bytes_type)  # type: ignore[operator]

    def test_png_content_type(self) -> None:
        """PNG files must be served with an image/png content-type header."""
        h = self._make_handler()
        h._serve_static("/ui/icon.png")
        self.assertIsNotNone(h._bytes_type)
        self.assertIn("png", h._bytes_type)  # type: ignore[operator]


if __name__ == "__main__":
    unittest.main()
