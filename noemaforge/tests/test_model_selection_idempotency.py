#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_model_selection_idempotency.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: Integration test: /api/model-selection/continue is idempotent — a second
  call with the same mode/composite_top_n returns the same job_id as the first.
Inputs: AdminGuiServer.model_selection_continue(), AdminGuiServer.create_job().
Outputs: unittest assertions only.
Side effects: None (temp dirs only).
Tests: python3 -m unittest noemaforge/tests/test_model_selection_idempotency.py -v
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from admin_gui_server import AdminGuiServer  # noqa: E402
from session_store import SessionStore  # noqa: E402
from event_log import EventLog  # noqa: E402
from noemaforge_version import RUNTIME_VERSION  # noqa: E402


def _make_full_server_stub(td: Path) -> AdminGuiServer:
    """Build a minimal AdminGuiServer stub sufficient for model_selection_continue()."""
    srv = object.__new__(AdminGuiServer)
    # Paths
    srv.jobs_dir = td / "jobs"
    srv.jobs_dir.mkdir(parents=True, exist_ok=True)
    srv.data_root = td
    srv.gui_state_dir = td / "gui"
    srv.gui_state_dir.mkdir(parents=True, exist_ok=True)
    srv.model_selection_state = td / "model_selection"
    srv.model_selection_state.mkdir(parents=True, exist_ok=True)
    srv.review_dir = td / "review"
    (srv.review_dir / "sr" / "inbox").mkdir(parents=True, exist_ok=True)
    (srv.review_dir / "ssr" / "inbox").mkdir(parents=True, exist_ok=True)
    # Stores
    srv.session_store = SessionStore(td / "sessions")
    srv.event_log = EventLog(td / "events")
    return srv


class TestModelSelectionContinueIdempotency(unittest.TestCase):
    """Two calls to model_selection_continue() with the same params return the same job_id."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory(prefix="nf_msc_idempotency_")
        self.td = Path(self._td.name)
        self.srv = _make_full_server_stub(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def _body(self, mode: str = "full_composite", n: int = 4) -> dict:
        return {"mode": mode, "composite_top_n": n}

    def test_first_call_returns_ok(self) -> None:
        result = self.srv.model_selection_continue(self._body())
        self.assertTrue(result["ok"])
        self.assertEqual(result["version"], RUNTIME_VERSION)

    def test_first_call_returns_job_with_id(self) -> None:
        result = self.srv.model_selection_continue(self._body())
        job = result.get("job")
        self.assertIsInstance(job, dict)
        self.assertIn("job_id", job)
        self.assertTrue(str(job["job_id"]))

    def test_second_call_returns_same_job_id(self) -> None:
        r1 = self.srv.model_selection_continue(self._body())
        r2 = self.srv.model_selection_continue(self._body())
        job_id_1 = r1["job"]["job_id"]
        job_id_2 = r2["job"]["job_id"]
        self.assertEqual(job_id_1, job_id_2,
                         f"Expected same job_id but got {job_id_1!r} vs {job_id_2!r}")

    def test_second_call_with_different_mode_has_different_idempotency_key(self) -> None:
        # Note: job_id values may collide within the same second (timestamp-based
        # generation); we test idempotency_key instead, which is mode-scoped.
        r1 = self.srv.model_selection_continue(self._body(mode="full_composite", n=4))
        r2 = self.srv.model_selection_continue(self._body(mode="normal"))
        key_1 = r1["job"]["idempotency_key"]
        key_2 = r2["job"]["idempotency_key"]
        self.assertNotEqual(key_1, key_2,
                            "Different mode must produce a different idempotency_key")

    def test_three_identical_calls_all_return_same_job_id(self) -> None:
        body = self._body()
        r1 = self.srv.model_selection_continue(body)
        r2 = self.srv.model_selection_continue(body)
        r3 = self.srv.model_selection_continue(body)
        ids = {r["job"]["job_id"] for r in (r1, r2, r3)}
        self.assertEqual(len(ids), 1, f"Expected 1 unique job_id, got: {ids}")

    def test_job_status_is_needs_privilege(self) -> None:
        result = self.srv.model_selection_continue(self._body())
        self.assertEqual(result["job"]["status"], "needs_privilege")

    def test_response_includes_privileged_runner_policy(self) -> None:
        result = self.srv.model_selection_continue(self._body())
        self.assertEqual(result.get("privileged_runner_policy"), "polkit_approval_required")

    def test_response_includes_suggested_command(self) -> None:
        result = self.srv.model_selection_continue(self._body())
        cmd = result.get("suggested_command") or ""
        self.assertIn("--keep-display", cmd)
        self.assertIn("noemaforge", cmd)

    def test_job_has_idempotency_key(self) -> None:
        result = self.srv.model_selection_continue(self._body())
        job = result["job"]
        self.assertIn("idempotency_key", job)
        self.assertTrue(job["idempotency_key"].startswith("model-selection-continue:"))

    def test_jobs_dir_has_one_job_file_after_two_calls(self) -> None:
        body = self._body()
        self.srv.model_selection_continue(body)
        self.srv.model_selection_continue(body)
        job_files = list((self.td / "jobs").glob("job_*.json"))
        self.assertEqual(len(job_files), 1,
                         f"Expected 1 job file, found {len(job_files)}: {[f.name for f in job_files]}")


class TestVaultReinventoryIdempotency(unittest.TestCase):
    """Two calls to vault_reinventory() return the same job_id."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory(prefix="nf_vault_idempotency_")
        self.td = Path(self._td.name)
        self.srv = _make_full_server_stub(self.td)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_first_call_returns_ok(self) -> None:
        result = self.srv.vault_reinventory()
        self.assertTrue(result["ok"])

    def test_second_call_returns_same_job_id(self) -> None:
        r1 = self.srv.vault_reinventory()
        r2 = self.srv.vault_reinventory()
        job_id_1 = r1["job"]["job_id"]
        job_id_2 = r2["job"]["job_id"]
        self.assertEqual(job_id_1, job_id_2,
                         f"vault_reinventory should be idempotent, got {job_id_1!r} vs {job_id_2!r}")

    def test_job_status_is_needs_privilege(self) -> None:
        result = self.srv.vault_reinventory()
        self.assertEqual(result["job"]["status"], "needs_privilege")


if __name__ == "__main__":
    unittest.main()
