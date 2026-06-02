#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_startup_preflight.py
Zone: test
Version: 0.32.2
Created: 2026-05-27
Modified: 2026-05-27
Purpose: TDD tests for startup_preflight module — storage, display/GDM, and journald gates.
Inputs: startup_preflight module (StorageCheck, DisplayCheck, JournaldCheck, PreflightSuite).
Outputs: test pass/fail.
Side effects: None (all subprocess calls are mocked).
Tests: python3 -m unittest noemaforge/tests/test_startup_preflight.py
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_SRC = Path(__file__).parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from startup_preflight import (  # noqa: E402
    CheckResult,
    DisplayCheck,
    JournaldCheck,
    PreflightSuite,
    StorageCheck,
)


# ---------------------------------------------------------------------------
# CheckResult
# ---------------------------------------------------------------------------

class TestCheckResult(unittest.TestCase):
    """CheckResult is a named tuple / dataclass with passed, name, details."""

    def test_passed_true(self) -> None:
        r = CheckResult(name="storage", passed=True, details="20 GB free")
        self.assertTrue(r.passed)

    def test_passed_false(self) -> None:
        r = CheckResult(name="storage", passed=False, details="only 2 GB free, need 10 GB")
        self.assertFalse(r.passed)

    def test_has_name(self) -> None:
        r = CheckResult(name="display", passed=True, details="")
        self.assertEqual(r.name, "display")

    def test_has_details(self) -> None:
        r = CheckResult(name="storage", passed=False, details="disk full")
        self.assertIn("disk full", r.details)

    def test_not_applicable_is_passing(self) -> None:
        r = CheckResult(name="display", passed=True, details="not applicable (non-Linux)")
        self.assertTrue(r.passed)

    def test_to_dict(self) -> None:
        r = CheckResult(name="storage", passed=True, details="ok")
        d = r.to_dict()
        self.assertIsInstance(d, dict)
        self.assertIn("name", d)
        self.assertIn("passed", d)
        self.assertIn("details", d)


# ---------------------------------------------------------------------------
# StorageCheck
# ---------------------------------------------------------------------------

class TestStorageCheck(unittest.TestCase):
    """StorageCheck verifies free disk space on given paths."""

    def test_check_passes_when_enough_space(self) -> None:
        check = StorageCheck(min_free_gb=1, paths=["/"])
        mock_usage = MagicMock()
        mock_usage.free = 100 * 1024 ** 3  # 100 GB free
        with patch("shutil.disk_usage", return_value=mock_usage):
            result = check.run()
        self.assertTrue(result.passed)

    def test_check_fails_when_too_little_space(self) -> None:
        check = StorageCheck(min_free_gb=50, paths=["/"])
        mock_usage = MagicMock()
        mock_usage.free = 5 * 1024 ** 3  # only 5 GB free
        with patch("shutil.disk_usage", return_value=mock_usage):
            result = check.run()
        self.assertFalse(result.passed)

    def test_details_include_free_space(self) -> None:
        check = StorageCheck(min_free_gb=10, paths=["/"])
        mock_usage = MagicMock()
        mock_usage.free = 15 * 1024 ** 3
        with patch("shutil.disk_usage", return_value=mock_usage):
            result = check.run()
        self.assertIn("15", result.details)

    def test_name_is_storage(self) -> None:
        check = StorageCheck(min_free_gb=10, paths=["/"])
        mock_usage = MagicMock()
        mock_usage.free = 20 * 1024 ** 3
        with patch("shutil.disk_usage", return_value=mock_usage):
            result = check.run()
        self.assertEqual(result.name, "storage")

    def test_check_multiple_paths_fails_when_one_low(self) -> None:
        check = StorageCheck(min_free_gb=10, paths=["/", "/mnt/data"])
        enough = MagicMock()
        enough.free = 100 * 1024 ** 3
        low = MagicMock()
        low.free = 2 * 1024 ** 3
        with patch("shutil.disk_usage", side_effect=[enough, low]):
            result = check.run()
        self.assertFalse(result.passed)

    def test_check_os_error_returns_fail(self) -> None:
        check = StorageCheck(min_free_gb=10, paths=["/nonexistent"])
        with patch("shutil.disk_usage", side_effect=OSError("no such path")):
            result = check.run()
        self.assertFalse(result.passed)
        self.assertIn("error", result.details.lower())


# ---------------------------------------------------------------------------
# DisplayCheck
# ---------------------------------------------------------------------------

class TestDisplayCheck(unittest.TestCase):
    """DisplayCheck verifies that the display manager service is running."""

    def test_passes_when_gdm_active(self) -> None:
        check = DisplayCheck(manager="gdm")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="active\n", stderr="")
            result = check.run()
        self.assertTrue(result.passed)

    def test_fails_when_gdm_inactive(self) -> None:
        check = DisplayCheck(manager="gdm")
        with patch("startup_preflight._is_linux", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=3, stdout="inactive\n", stderr="")
                result = check.run()
        self.assertFalse(result.passed)

    def test_name_is_display(self) -> None:
        check = DisplayCheck(manager="gdm")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="active\n", stderr="")
            result = check.run()
        self.assertEqual(result.name, "display")

    def test_non_linux_passes_with_not_applicable(self) -> None:
        check = DisplayCheck(manager="gdm")
        with patch("startup_preflight._is_linux", return_value=False):
            result = check.run()
        self.assertTrue(result.passed)
        self.assertIn("not applicable", result.details)

    def test_subprocess_error_returns_fail(self) -> None:
        check = DisplayCheck(manager="gdm")
        import subprocess
        with patch("startup_preflight._is_linux", return_value=True):
            with patch("subprocess.run", side_effect=FileNotFoundError("systemctl not found")):
                result = check.run()
        self.assertFalse(result.passed)

    def test_details_include_manager_name(self) -> None:
        check = DisplayCheck(manager="gdm3")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="active\n", stderr="")
            result = check.run()
        self.assertIn("gdm3", result.details)


# ---------------------------------------------------------------------------
# JournaldCheck
# ---------------------------------------------------------------------------

class TestJournaldCheck(unittest.TestCase):
    """JournaldCheck verifies journald is not in a degraded state."""

    def test_passes_when_no_errors(self) -> None:
        check = JournaldCheck()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="0\n", stderr="")
            result = check.run()
        self.assertTrue(result.passed)

    def test_fails_when_error_count_high(self) -> None:
        check = JournaldCheck(max_errors=5)
        # Simulate 100 error lines returned by journalctl.
        many_lines = "\n".join(f"error line {i}" for i in range(100))
        with patch("startup_preflight._is_linux", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=many_lines, stderr="")
                result = check.run()
        self.assertFalse(result.passed)

    def test_passes_when_error_count_within_limit(self) -> None:
        check = JournaldCheck(max_errors=10)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="3\n", stderr="")
            result = check.run()
        self.assertTrue(result.passed)

    def test_name_is_journald(self) -> None:
        check = JournaldCheck()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="0\n", stderr="")
            result = check.run()
        self.assertEqual(result.name, "journald")

    def test_non_linux_passes(self) -> None:
        check = JournaldCheck()
        with patch("startup_preflight._is_linux", return_value=False):
            result = check.run()
        self.assertTrue(result.passed)

    def test_subprocess_error_is_warning_not_fail(self) -> None:
        """journald check failure is non-fatal — returns passed=True with warning."""
        check = JournaldCheck()
        with patch("startup_preflight._is_linux", return_value=True):
            with patch("subprocess.run", side_effect=FileNotFoundError("journalctl not found")):
                result = check.run()
        # journald unavailable → pass with warning (don't block first-start)
        self.assertTrue(result.passed)
        self.assertIn("warn", result.details.lower())


# ---------------------------------------------------------------------------
# PreflightSuite
# ---------------------------------------------------------------------------

class TestPreflightSuite(unittest.TestCase):
    """PreflightSuite runs multiple checks and aggregates results."""

    def test_suite_all_pass(self) -> None:
        suite = PreflightSuite(checks=[
            StorageCheck(min_free_gb=1, paths=["/"]),
        ])
        mock_usage = MagicMock()
        mock_usage.free = 100 * 1024 ** 3
        with patch("shutil.disk_usage", return_value=mock_usage):
            report = suite.run()
        self.assertTrue(report["ok"])

    def test_suite_one_fails(self) -> None:
        suite = PreflightSuite(checks=[
            StorageCheck(min_free_gb=100, paths=["/"]),
        ])
        mock_usage = MagicMock()
        mock_usage.free = 1 * 1024 ** 3
        with patch("shutil.disk_usage", return_value=mock_usage):
            report = suite.run()
        self.assertFalse(report["ok"])

    def test_suite_report_has_checks_list(self) -> None:
        suite = PreflightSuite(checks=[StorageCheck(min_free_gb=1, paths=["/"])])
        mock_usage = MagicMock()
        mock_usage.free = 50 * 1024 ** 3
        with patch("shutil.disk_usage", return_value=mock_usage):
            report = suite.run()
        self.assertIn("checks", report)
        self.assertIsInstance(report["checks"], list)

    def test_suite_report_has_version(self) -> None:
        from noemaforge_version import RUNTIME_VERSION
        suite = PreflightSuite(checks=[])
        report = suite.run()
        self.assertEqual(report["version"], RUNTIME_VERSION)

    def test_default_suite_for_first_start(self) -> None:
        """PreflightSuite.for_first_start() factory returns a runnable suite."""
        suite = PreflightSuite.for_first_start()
        self.assertIsNotNone(suite)
        self.assertGreater(len(suite.checks), 0)

    def test_suite_empty_is_ok(self) -> None:
        suite = PreflightSuite(checks=[])
        report = suite.run()
        self.assertTrue(report["ok"])


if __name__ == "__main__":
    unittest.main()
