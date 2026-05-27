#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_admin_gui_preflight_wiring.py
Zone: test
Version: 0.32.2
Created: 2026-05-27
Modified: 2026-05-27
Purpose: TDD tests for PreflightSuite wiring into AdminGuiServer — gates
  model_selection_continue() and vault_reinventory() before job creation.
Inputs: admin_gui_server.AdminGuiServer, startup_preflight.PreflightSuite.
Outputs: test pass/fail.
Side effects: Creates and removes temporary directories.
Tests: python3 -m unittest noemaforge/tests/test_admin_gui_preflight_wiring.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from admin_gui_server import AdminGuiServer  # noqa: E402
from job_manager import JobManager  # noqa: E402
from noemaforge_version import RUNTIME_VERSION  # noqa: E402


# ---------------------------------------------------------------------------
# Shared stub factory
# ---------------------------------------------------------------------------

def _stub_server(td: Path) -> AdminGuiServer:
    """Build a minimal AdminGuiServer stub for preflight-wiring tests."""
    srv = object.__new__(AdminGuiServer)
    srv.jobs_dir = td / "jobs"
    srv.jobs_dir.mkdir(parents=True, exist_ok=True)
    srv.job_manager = JobManager(srv.jobs_dir)
    srv.data_root = td
    # model_selection_continue writes into this directory.
    srv.model_selection_state = td / "model_selection"
    srv.model_selection_state.mkdir(parents=True, exist_ok=True)
    # vault_reinventory writes into data_root/vault/.
    (td / "vault").mkdir(parents=True, exist_ok=True)
    return srv


def _fail_report(**extra) -> dict:
    report = {
        "ok": False,
        "version": RUNTIME_VERSION,
        "checks": [
            {"name": "storage", "passed": False, "details": "only 2 GB free, need 10 GB"},
        ],
    }
    report.update(extra)
    return report


def _pass_report() -> dict:
    return {
        "ok": True,
        "version": RUNTIME_VERSION,
        "checks": [
            {"name": "storage", "passed": True, "details": "100 GB free"},
            {"name": "display", "passed": True, "details": "gdm is active"},
            {"name": "journald", "passed": True, "details": "0 error lines"},
        ],
    }


# ---------------------------------------------------------------------------
# _run_preflight() unit tests
# ---------------------------------------------------------------------------

class TestRunPreflightMethod(unittest.TestCase):
    """AdminGuiServer._run_preflight() wraps PreflightSuite.for_first_start().run()."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.srv = _stub_server(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_returns_none_when_preflight_passes(self) -> None:
        with patch("admin_gui_server.PreflightSuite") as MockSuite:
            inst = MagicMock()
            inst.run.return_value = _pass_report()
            MockSuite.for_first_start.return_value = inst
            result = self.srv._run_preflight()
        self.assertIsNone(result)

    def test_returns_report_when_preflight_fails(self) -> None:
        with patch("admin_gui_server.PreflightSuite") as MockSuite:
            inst = MagicMock()
            inst.run.return_value = _fail_report()
            MockSuite.for_first_start.return_value = inst
            result = self.srv._run_preflight()
        self.assertIsNotNone(result)
        self.assertFalse(result["ok"])  # type: ignore[index]

    def test_returned_report_includes_checks(self) -> None:
        with patch("admin_gui_server.PreflightSuite") as MockSuite:
            inst = MagicMock()
            inst.run.return_value = _fail_report()
            MockSuite.for_first_start.return_value = inst
            result = self.srv._run_preflight()
        self.assertIn("checks", result)  # type: ignore[arg-type]

    def test_exception_returns_none_nonfatal(self) -> None:
        """If PreflightSuite itself raises, _run_preflight must not crash the server."""
        with patch("admin_gui_server.PreflightSuite") as MockSuite:
            MockSuite.for_first_start.side_effect = Exception("boom")
            result = self.srv._run_preflight()
        self.assertIsNone(result)

    def test_calls_for_first_start_classmethod(self) -> None:
        with patch("admin_gui_server.PreflightSuite") as MockSuite:
            inst = MagicMock()
            inst.run.return_value = _pass_report()
            MockSuite.for_first_start.return_value = inst
            self.srv._run_preflight()
        MockSuite.for_first_start.assert_called_once()


# ---------------------------------------------------------------------------
# model_selection_continue() preflight gate
# ---------------------------------------------------------------------------

class TestModelSelectionContinuePreflight(unittest.TestCase):
    """model_selection_continue() runs preflight before creating a job."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.srv = _stub_server(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_returns_not_ok_when_preflight_fails(self) -> None:
        self.srv._run_preflight = MagicMock(return_value=_fail_report())
        result = self.srv.model_selection_continue({"mode": "full_composite"})
        self.assertFalse(result["ok"])

    def test_sets_preflight_failed_flag(self) -> None:
        self.srv._run_preflight = MagicMock(return_value=_fail_report())
        result = self.srv.model_selection_continue({"mode": "full_composite"})
        self.assertTrue(result.get("preflight_failed"))

    def test_includes_preflight_report_in_response(self) -> None:
        report = _fail_report()
        self.srv._run_preflight = MagicMock(return_value=report)
        result = self.srv.model_selection_continue({"mode": "full_composite"})
        self.assertIn("preflight", result)
        self.assertEqual(result["preflight"], report)

    def test_no_job_created_when_preflight_fails(self) -> None:
        self.srv._run_preflight = MagicMock(return_value=_fail_report())
        self.srv.model_selection_continue({"mode": "full_composite"})
        self.assertEqual(len(self.srv.job_manager.list_active()), 0)

    def test_includes_version_in_failure_response(self) -> None:
        self.srv._run_preflight = MagicMock(return_value=_fail_report())
        result = self.srv.model_selection_continue({"mode": "full_composite"})
        self.assertEqual(result.get("version"), RUNTIME_VERSION)

    def test_proceeds_normally_when_preflight_passes(self) -> None:
        self.srv._run_preflight = MagicMock(return_value=None)
        progress = {"tested_models": 0, "total_models": 5, "failed_models": 0, "remaining_models": 5}
        with patch.object(self.srv, "model_selection_progress", return_value=progress):
            with patch.object(self.srv, "_write_json", return_value=None):
                with patch.object(self.srv, "save_message", return_value=None):
                    with patch("admin_gui_server.enrich_privileged_job", side_effect=lambda job, **kw: job):
                        result = self.srv.model_selection_continue({"mode": "full_composite", "composite_top_n": 4})
        self.assertTrue(result["ok"])

    def test_creates_job_when_preflight_passes(self) -> None:
        self.srv._run_preflight = MagicMock(return_value=None)
        progress = {"tested_models": 0, "total_models": 5, "failed_models": 0, "remaining_models": 5}
        with patch.object(self.srv, "model_selection_progress", return_value=progress):
            with patch.object(self.srv, "_write_json", return_value=None):
                with patch.object(self.srv, "save_message", return_value=None):
                    with patch("admin_gui_server.enrich_privileged_job", side_effect=lambda job, **kw: job):
                        self.srv.model_selection_continue({"mode": "full_composite", "composite_top_n": 4})
        jobs = self.srv.job_manager.list_all()
        self.assertGreater(len(jobs), 0)
        self.assertEqual(jobs[0]["kind"], "model_selection_continue")


# ---------------------------------------------------------------------------
# vault_reinventory() preflight gate
# ---------------------------------------------------------------------------

class TestVaultReinventoryPreflight(unittest.TestCase):
    """vault_reinventory() runs preflight before creating a job."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.srv = _stub_server(Path(self._td.name))

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_returns_not_ok_when_preflight_fails(self) -> None:
        self.srv._run_preflight = MagicMock(return_value=_fail_report())
        result = self.srv.vault_reinventory()
        self.assertFalse(result["ok"])

    def test_sets_preflight_failed_flag(self) -> None:
        self.srv._run_preflight = MagicMock(return_value=_fail_report())
        result = self.srv.vault_reinventory()
        self.assertTrue(result.get("preflight_failed"))

    def test_includes_preflight_report_in_response(self) -> None:
        report = _fail_report()
        self.srv._run_preflight = MagicMock(return_value=report)
        result = self.srv.vault_reinventory()
        self.assertIn("preflight", result)
        self.assertEqual(result["preflight"], report)

    def test_no_job_created_when_preflight_fails(self) -> None:
        self.srv._run_preflight = MagicMock(return_value=_fail_report())
        self.srv.vault_reinventory()
        self.assertEqual(len(self.srv.job_manager.list_active()), 0)

    def test_includes_version_in_failure_response(self) -> None:
        self.srv._run_preflight = MagicMock(return_value=_fail_report())
        result = self.srv.vault_reinventory()
        self.assertEqual(result.get("version"), RUNTIME_VERSION)

    def test_proceeds_normally_when_preflight_passes(self) -> None:
        self.srv._run_preflight = MagicMock(return_value=None)
        progress = {"tested_models": 0, "total_models": 5, "failed_models": 0, "remaining_models": 5}
        with patch.object(self.srv, "model_selection_progress", return_value=progress):
            with patch.object(self.srv, "_write_json", return_value=None):
                with patch.object(self.srv, "save_message", return_value=None):
                    with patch("admin_gui_server.enrich_privileged_job", side_effect=lambda job, **kw: job):
                        result = self.srv.vault_reinventory()
        self.assertTrue(result["ok"])

    def test_creates_job_when_preflight_passes(self) -> None:
        self.srv._run_preflight = MagicMock(return_value=None)
        progress = {"tested_models": 0, "total_models": 5, "failed_models": 0, "remaining_models": 5}
        with patch.object(self.srv, "model_selection_progress", return_value=progress):
            with patch.object(self.srv, "_write_json", return_value=None):
                with patch.object(self.srv, "save_message", return_value=None):
                    with patch("admin_gui_server.enrich_privileged_job", side_effect=lambda job, **kw: job):
                        self.srv.vault_reinventory()
        jobs = self.srv.job_manager.list_all()
        self.assertGreater(len(jobs), 0)
        self.assertEqual(jobs[0]["kind"], "vault_reinventory")


if __name__ == "__main__":
    unittest.main()
