"""Tests for service_manager — cross-platform service-manager abstraction."""
from __future__ import annotations

import sys
import unittest
import unittest.mock

import service_manager


class TestAvailableNonLinux(unittest.TestCase):
    def setUp(self):
        service_manager._cached_available = None

    def tearDown(self):
        service_manager._cached_available = None

    def test_unavailable_on_non_linux(self):
        with unittest.mock.patch.object(sys, "platform", "win32"):
            result = service_manager.available()
        self.assertFalse(result)

    def test_unavailable_on_darwin(self):
        with unittest.mock.patch.object(sys, "platform", "darwin"):
            result = service_manager.available()
        self.assertFalse(result)


class TestCallUnavailable(unittest.TestCase):
    def setUp(self):
        service_manager._cached_available = None

    def tearDown(self):
        service_manager._cached_available = None

    def test_call_returns_127_when_unavailable(self):
        with unittest.mock.patch.object(sys, "platform", "win32"):
            rc = service_manager.call("is-active", "some.service")
        self.assertEqual(rc, service_manager.SERVICE_MANAGER_UNAVAILABLE)

    def test_check_output_returns_unavailable_when_not_linux(self):
        with unittest.mock.patch.object(sys, "platform", "darwin"):
            rc, out = service_manager.check_output(["is-active", "some.service"])
        self.assertEqual(rc, service_manager.SERVICE_MANAGER_UNAVAILABLE)
        self.assertEqual(out, "service_manager_not_available")


class TestCallAvailable(unittest.TestCase):
    def setUp(self):
        service_manager._cached_available = True

    def tearDown(self):
        service_manager._cached_available = None

    def test_call_delegates_to_subprocess(self):
        with unittest.mock.patch("subprocess.call", return_value=0) as mock_call:
            rc = service_manager.call("is-active", "noemaforge-llm-gateway.service")
        self.assertEqual(rc, 0)
        mock_call.assert_called_once_with(
            ["systemctl", "is-active", "noemaforge-llm-gateway.service"],
            stdout=unittest.mock.ANY,
            stderr=unittest.mock.ANY,
        )

    def test_check_output_success(self):
        with unittest.mock.patch("subprocess.check_output", return_value=b"active\n"):
            rc, out = service_manager.check_output(["is-active", "foo.service"])
        self.assertEqual(rc, 0)
        self.assertIn("active", out)

    def test_check_output_nonzero(self):
        import subprocess
        exc = subprocess.CalledProcessError(3, ["systemctl"], output=b"inactive\n")
        with unittest.mock.patch("subprocess.check_output", side_effect=exc):
            rc, out = service_manager.check_output(["is-active", "foo.service"])
        self.assertEqual(rc, 3)
        self.assertIn("inactive", out)

    def test_call_returns_127_on_oserror(self):
        with unittest.mock.patch("subprocess.call", side_effect=OSError("no such file")):
            rc = service_manager.call("start", "foo.service")
        self.assertEqual(rc, service_manager.SERVICE_MANAGER_UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
