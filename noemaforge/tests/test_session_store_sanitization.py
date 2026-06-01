#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_session_store_sanitization.py
Zone: tests
Version: 0.32.2
Created: 2026-05-31
Modified: 2026-05-31
Purpose: Direct unit tests for SessionStore path sanitization and mode validation:
           - _session_path(): sanitizes session_id to a safe filename so that
             path traversal chars cannot escape root.
           - set_mode(): rejects invalid mode strings → "normal" fallback.
           - attach_active_jobs(): filters out non-dict items.
         These behaviors are security-relevant (_session_path) and correctness-
         critical (set_mode). Previously only tested indirectly through higher-
         level API tests.
Inputs: SessionStore from session_store.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp().
Tests: python3 -m unittest noemaforge/tests/test_session_store_sanitization.py -v
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

    def _norm(r):
        r.setdefault("session_id", "default")
        r.setdefault("messages", [])
        r.setdefault("selected_mode", "normal")
        r.setdefault("selected_composite_top_n", 0)
        r.setdefault("active_jobs", [])
        return r

    stub_orch.normalize_session_record = _norm
    sys.modules.setdefault("orchestration_state", stub_orch)


_install_stubs()

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from session_store import SessionStore  # noqa: E402


class TestSessionPath(unittest.TestCase):
    """SessionStore._session_path() must produce safe file names."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.store = SessionStore(root=Path(self._tmpdir))

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _path(self, session_id: str) -> Path:
        return self.store._session_path(session_id)

    # --- Stays within root -----------------------------------------------

    def test_normal_id_creates_json_file(self) -> None:
        """A clean alphanumeric session_id produces a .json file in root."""
        p = self._path("mysession")
        self.assertEqual(p.parent, self.store.root)
        self.assertTrue(p.name.endswith(".json"))

    def test_default_id_is_default_json(self) -> None:
        """The default session_id 'default' maps to 'default.json'."""
        p = self._path("default")
        self.assertEqual(p.name, "default.json")

    def test_path_is_within_root(self) -> None:
        """Resolved path must be inside the store root directory."""
        for sid in ("default", "user_1", "session.2026"):
            p = self._path(sid).resolve()
            self.assertTrue(
                str(p).startswith(str(self.store.root)),
                f"_session_path({sid!r}) must stay within root",
            )

    # --- Traversal protection --------------------------------------------

    def test_slash_replaced_in_session_id(self) -> None:
        """Forward slash in session_id is replaced (cannot create subdirectory)."""
        p = self._path("sub/dir")
        self.assertNotIn("/", p.name, "Forward slash must not appear in filename")

    def test_dotdot_does_not_escape_root(self) -> None:
        """'../evil' session_id must not escape root directory."""
        p = self._path("../evil")
        # The file is in root, not parent
        self.assertEqual(p.parent.resolve(), self.store.root.resolve())

    def test_long_session_id_truncated(self) -> None:
        """Session IDs longer than 96 chars are truncated in the filename."""
        long_id = "a" * 200
        p = self._path(long_id)
        # The filename minus '.json' should be at most 96 chars
        stem = p.stem
        self.assertLessEqual(len(stem), 96, "Session ID must be truncated to 96 chars")

    def test_empty_session_id_defaults(self) -> None:
        """An empty session_id falls back to 'default'."""
        p = self._path("")
        self.assertEqual(p.name, "default.json")

    def test_none_session_id_defaults(self) -> None:
        """None-equivalent session_id falls back to 'default'."""
        # None is handled via `str(session_id or "default")`
        p = self.store._session_path(None)  # type: ignore[arg-type]
        self.assertEqual(p.name, "default.json")

    # --- Functional: load/save use _session_path correctly ---------------

    def test_load_creates_file_at_session_path(self) -> None:
        """load() creates a file at exactly the _session_path() location."""
        self.store.load("mysession")
        expected = self._path("mysession")
        self.assertTrue(expected.exists(), "load() must create session file at _session_path()")

    def test_load_traversal_id_stays_in_root(self) -> None:
        """load() with traversal session_id must create file inside root."""
        self.store.load("../evil_session")
        # No file should exist outside root
        evil_path = Path(self._tmpdir).parent / "evil_session.json"
        self.assertFalse(evil_path.exists(), "Traversal session_id must not escape root")


class TestSetMode(unittest.TestCase):
    """SessionStore.set_mode() must enforce allowed modes."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.store = SessionStore(root=Path(self._tmpdir))

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_normal_mode_accepted(self) -> None:
        """'normal' is an allowed mode."""
        session = self.store.set_mode("default", "normal")
        self.assertEqual(session["selected_mode"], "normal")

    def test_fast_mode_accepted(self) -> None:
        """'fast' is an allowed mode."""
        session = self.store.set_mode("default", "fast")
        self.assertEqual(session["selected_mode"], "fast")

    def test_full_mode_accepted(self) -> None:
        """'full' is an allowed mode."""
        session = self.store.set_mode("default", "full")
        self.assertEqual(session["selected_mode"], "full")

    def test_full_composite_mode_accepted(self) -> None:
        """'full_composite' is an allowed mode."""
        session = self.store.set_mode("default", "full_composite")
        self.assertEqual(session["selected_mode"], "full_composite")

    def test_invalid_mode_falls_back_to_normal(self) -> None:
        """Any mode string not in the allowed set falls back to 'normal'."""
        for bad_mode in ("admin", "FULL", "full composite", "", "../../", "injection"):
            with self.subTest(mode=bad_mode):
                session = self.store.set_mode("default", bad_mode)
                self.assertEqual(
                    session["selected_mode"], "normal",
                    f"Invalid mode {bad_mode!r} must fall back to 'normal'"
                )

    def test_composite_top_n_persisted(self) -> None:
        """composite_top_n is persisted alongside mode."""
        session = self.store.set_mode("default", "full_composite", composite_top_n=5)
        self.assertEqual(session.get("selected_composite_top_n"), 5)

    def test_composite_top_n_defaults_to_zero(self) -> None:
        """composite_top_n defaults to 0 when not supplied."""
        session = self.store.set_mode("default", "normal")
        self.assertEqual(session.get("selected_composite_top_n"), 0)


class TestAttachActiveJobs(unittest.TestCase):
    """SessionStore.attach_active_jobs() must filter non-dict items."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.store = SessionStore(root=Path(self._tmpdir))

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_dict_jobs_persisted(self) -> None:
        """Dict jobs are persisted as active_jobs."""
        jobs = [{"job_id": "j1", "status": "running"}, {"job_id": "j2", "status": "queued"}]
        session = self.store.attach_active_jobs("default", jobs)
        self.assertEqual(len(session.get("active_jobs", [])), 2)

    def test_non_dict_items_filtered_out(self) -> None:
        """Non-dict items (strings, ints, None) must be filtered from active_jobs."""
        jobs = [{"job_id": "j1"}, "not a dict", 42, None, {"job_id": "j2"}]
        session = self.store.attach_active_jobs("default", jobs)
        active = session.get("active_jobs", [])
        self.assertEqual(len(active), 2, "Only dict items must be persisted as active_jobs")
        for job in active:
            self.assertIsInstance(job, dict)

    def test_empty_list_clears_jobs(self) -> None:
        """Attaching an empty list must clear active_jobs."""
        self.store.attach_active_jobs("default", [{"job_id": "j1"}])
        session = self.store.attach_active_jobs("default", [])
        self.assertEqual(session.get("active_jobs", []), [])


if __name__ == "__main__":
    unittest.main()
