#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_gui_utils.py
Zone: tests
Version: 0.32.2
Created: 2026-05-31
Modified: 2026-05-31
Purpose: Unit tests for security-relevant admin_gui_server utility functions:
           - safe_id(): path-safe ID construction used for job files, avatar
             paths, and artifact names.  A regression (allowing '..' or '/')
             would re-introduce path traversal in every caller.
           - resolve_artifact_path(): containment guard that keeps artifact
             access within allowed roots.  Failure here would allow arbitrary
             file reads via /api/artifacts/open and /api/artifacts/download.
         Tests use source stubs so no HTTP server is needed.
Inputs: admin_gui_server.safe_id, AdminGuiServer.resolve_artifact_path.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_admin_gui_utils.py -v
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

from admin_gui_server import safe_id, AdminGuiServer  # noqa: E402


# ---------------------------------------------------------------------------
# Tests for safe_id()
# ---------------------------------------------------------------------------

class TestSafeId(unittest.TestCase):
    """safe_id() must produce path-safe IDs under all inputs."""

    def test_normal_alphanumeric_unchanged(self) -> None:
        """Normal alphanumeric strings pass through unchanged."""
        self.assertEqual(safe_id("hello123"), "hello123")

    def test_spaces_replaced_with_hyphens(self) -> None:
        """Spaces are replaced by hyphens."""
        self.assertEqual(safe_id("hello world"), "hello-world")

    def test_slashes_replaced_with_hyphens(self) -> None:
        """Forward and backward slashes are replaced (path separators blocked)."""
        result = safe_id("path/to/file")
        self.assertNotIn("/", result, "Forward slash must not survive safe_id()")
        self.assertNotIn("\\", result, "Backslash must not survive safe_id()")

    def test_dotdot_produces_no_separator(self) -> None:
        """'..' sequences must not produce a usable traversal ID."""
        result = safe_id("..")
        # '..' → after regex: '..' → after strip('-._'): '' → default 'item'
        self.assertEqual(result, "item",
                         "'..' must collapse to the default 'item' after stripping dots")

    def test_traversal_sequence_sanitized(self) -> None:
        """'../etc/passwd' must not contain traversal after safe_id()."""
        result = safe_id("../etc/passwd")
        self.assertNotIn("..", result, "'..' must be eliminated by safe_id()")
        self.assertNotIn("/", result, "'/' must be replaced by safe_id()")
        # Must not be empty
        self.assertTrue(result, "safe_id() must return a non-empty string for a non-trivial input")

    def test_empty_string_returns_default(self) -> None:
        """Empty string returns the default value."""
        self.assertEqual(safe_id(""), "item")
        self.assertEqual(safe_id("", default="fallback"), "fallback")

    def test_whitespace_only_returns_default(self) -> None:
        """Whitespace-only string returns the default value."""
        self.assertEqual(safe_id("   "), "item")

    def test_all_special_chars_returns_default(self) -> None:
        """String of only special chars becomes empty → returns default."""
        result = safe_id("---...___---")
        self.assertEqual(result, "item",
                         "All-special string must collapse to default after stripping")

    def test_long_string_truncated_at_96(self) -> None:
        """Strings longer than 96 chars are truncated."""
        long = "a" * 200
        result = safe_id(long)
        self.assertEqual(len(result), 96, "safe_id() must truncate to 96 characters")
        self.assertEqual(result, "a" * 96)

    def test_exactly_96_chars_not_truncated(self) -> None:
        """A 96-character string is returned verbatim."""
        exact = "a" * 96
        self.assertEqual(safe_id(exact), exact)

    def test_97_chars_truncated(self) -> None:
        """A 97-character string is truncated to 96."""
        over = "a" * 97
        self.assertEqual(len(safe_id(over)), 96)

    def test_unsafe_job_id_sanitized(self) -> None:
        """'../unsafe job' → no traversal, no space."""
        result = safe_id("../unsafe job")
        self.assertNotIn("..", result)
        self.assertNotIn("/", result)
        self.assertNotIn(" ", result)

    def test_custom_default_returned_for_empty(self) -> None:
        """Custom default parameter is returned when all chars are stripped."""
        result = safe_id("...", default="safe_default")
        self.assertEqual(result, "safe_default")


# ---------------------------------------------------------------------------
# Tests for resolve_artifact_path()
# ---------------------------------------------------------------------------

class TestResolveArtifactPath(unittest.TestCase):
    """resolve_artifact_path() must enforce containment in allowed roots."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.data_root = Path(self._tmpdir) / "data"
        self.data_root.mkdir()
        # Create a file inside the allowed root
        self.artifact = self.data_root / "report.txt"
        self.artifact.write_text("hello", encoding="utf-8")
        # Create a directory with a file
        (self.data_root / "subdir").mkdir()
        (self.data_root / "subdir" / "nested.json").write_text("{}", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_server(self) -> AdminGuiServer:
        """Stub server with only the attributes needed by resolve_artifact_path."""
        srv = object.__new__(AdminGuiServer)
        srv.data_root = self.data_root
        # Other roots — point them at the same data_root or non-existent paths
        srv.state = self.data_root / "state"
        srv.model_selection_state = self.data_root / "model"
        srv.evolution_state = self.data_root / "evolution"
        srv.dev_team_state = self.data_root / "dev_team"
        return srv

    # --- Rejection cases --------------------------------------------------

    def test_empty_path_rejected(self) -> None:
        """Empty path string must return ok=False."""
        srv = self._make_server()
        result = srv.resolve_artifact_path("")
        self.assertFalse(result["ok"])

    def test_tilde_path_rejected(self) -> None:
        """Paths starting with '~' must be rejected (home expansion blocked)."""
        srv = self._make_server()
        result = srv.resolve_artifact_path("~/sensitive")
        self.assertFalse(result["ok"])

    def test_relative_path_rejected(self) -> None:
        """Relative paths must return ok=False."""
        srv = self._make_server()
        result = srv.resolve_artifact_path("relative/path")
        self.assertFalse(result["ok"])

    def test_absolute_path_outside_roots_rejected(self) -> None:
        """Absolute path outside allowed roots must return ok=False."""
        srv = self._make_server()
        # Use a path that IS absolute on all platforms but is outside data_root.
        # We create a sibling directory so it exists (skipping "not found" branch).
        outside_dir = Path(self._tmpdir) / "outside"
        outside_dir.mkdir(exist_ok=True)
        outside_file = outside_dir / "secret.txt"
        outside_file.write_text("secret", encoding="utf-8")
        result = srv.resolve_artifact_path(str(outside_file))
        self.assertFalse(result["ok"])
        self.assertIn("outside allowed roots", result.get("error", ""))

    def test_traversal_via_double_dot_rejected(self) -> None:
        """Traversal path resolving outside data_root must return ok=False."""
        srv = self._make_server()
        # /data/../etc/passwd → resolves to /etc/passwd → outside data_root
        traversal = str(self.data_root / ".." / ".." / "etc" / "passwd")
        result = srv.resolve_artifact_path(traversal)
        self.assertFalse(result["ok"])

    def test_nonexistent_file_in_allowed_root_rejected(self) -> None:
        """Allowed root path to non-existent file must return ok=False."""
        srv = self._make_server()
        result = srv.resolve_artifact_path(str(self.data_root / "ghost.txt"))
        self.assertFalse(result["ok"])
        self.assertIn("artifact not found", result.get("error", ""))

    # --- Success cases ----------------------------------------------------

    def test_valid_file_inside_root_accepted(self) -> None:
        """Absolute path to existing file inside data_root must return ok=True."""
        srv = self._make_server()
        result = srv.resolve_artifact_path(str(self.artifact))
        self.assertTrue(result["ok"])
        self.assertFalse(result.get("is_dir"), "Report.txt must not be flagged as directory")

    def test_result_includes_path_and_size(self) -> None:
        """Successful resolve must include path and size fields."""
        srv = self._make_server()
        result = srv.resolve_artifact_path(str(self.artifact))
        self.assertIn("path", result)
        self.assertIn("size", result)
        self.assertGreater(result["size"], 0)

    def test_directory_inside_root_accepted(self) -> None:
        """An existing directory inside data_root must return ok=True with is_dir=True."""
        srv = self._make_server()
        result = srv.resolve_artifact_path(str(self.data_root / "subdir"))
        self.assertTrue(result["ok"])
        self.assertTrue(result.get("is_dir"))


if __name__ == "__main__":
    unittest.main()
