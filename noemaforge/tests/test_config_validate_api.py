#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_config_validate_api.py
Zone: release/package
Version: 0.32.2
Created: 2026-05-30
Modified: 2026-05-30
Purpose: TDD tests for GET /api/config/validate wired via config_validator.py.
Inputs: ConfigValidator, AdminGuiServer.config_validate_api().
Outputs: unittest assertions only.
Side effects: None (temp dirs only).
Tests: python3 -m unittest noemaforge/tests/test_config_validate_api.py -v
Notes: Code comments are English-only; user-facing localized text belongs in docs/i18n or locale JSON files.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # noemaforge/
sys.path.insert(0, str(ROOT / "src"))

from noemaforge_version import RUNTIME_VERSION
from config_validator import ConfigValidator, ValidationReport
import admin_gui_server
from admin_gui_server import AdminGuiServer


# ---------------------------------------------------------------------------
# Unit: AdminGuiServer.config_validate_api()
# ---------------------------------------------------------------------------

class TestConfigValidateApiMethod(unittest.TestCase):
    """config_validate_api() returns {ok, version, report}."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="nf_cvapi_method_")
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_server_stub(self, scan_root: Path | None = None) -> AdminGuiServer:
        """Instantiate AdminGuiServer without socket binding."""
        obj = object.__new__(AdminGuiServer)
        obj._config_validate_root = scan_root or self.tmp_path
        return obj

    def test_returns_ok_flag(self) -> None:
        srv = self._make_server_stub()
        result = srv.config_validate_api()
        self.assertIn("ok", result)

    def test_returns_runtime_version(self) -> None:
        srv = self._make_server_stub()
        result = srv.config_validate_api()
        self.assertEqual(result["version"], RUNTIME_VERSION)

    def test_returns_report_dict(self) -> None:
        srv = self._make_server_stub()
        result = srv.config_validate_api()
        self.assertIn("report", result)
        self.assertIsInstance(result["report"], dict)

    def test_report_has_required_fields(self) -> None:
        srv = self._make_server_stub()
        report = srv.config_validate_api()["report"]
        self.assertIn("ok", report)
        self.assertIn("files_checked", report)
        self.assertIn("json_checked", report)
        self.assertIn("yaml_checked", report)
        self.assertIn("errors", report)

    def test_empty_dir_returns_ok_true_zero_files(self) -> None:
        srv = self._make_server_stub()
        result = srv.config_validate_api()
        self.assertTrue(result["ok"])
        self.assertEqual(result["report"]["files_checked"], 0)

    def test_valid_json_file_returns_ok_true(self) -> None:
        (self.tmp_path / "good.json").write_text('{"key": "value"}', encoding="utf-8")
        srv = self._make_server_stub()
        result = srv.config_validate_api()
        self.assertTrue(result["ok"])
        self.assertEqual(result["report"]["json_checked"], 1)
        self.assertEqual(result["report"]["errors"], [])

    def test_invalid_json_file_returns_ok_false(self) -> None:
        (self.tmp_path / "bad.json").write_text("{bad json}", encoding="utf-8")
        srv = self._make_server_stub()
        result = srv.config_validate_api()
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["report"]["errors"]), 1)

    def test_mixed_valid_invalid_returns_ok_false(self) -> None:
        (self.tmp_path / "ok.json").write_text('{"a": 1}', encoding="utf-8")
        (self.tmp_path / "bad.json").write_text("{broken}", encoding="utf-8")
        srv = self._make_server_stub()
        result = srv.config_validate_api()
        self.assertFalse(result["ok"])
        self.assertEqual(result["report"]["json_checked"], 2)

    def test_valid_yaml_file_returns_ok_true(self) -> None:
        (self.tmp_path / "good.yaml").write_text("key: value\n", encoding="utf-8")
        srv = self._make_server_stub()
        result = srv.config_validate_api()
        self.assertTrue(result["ok"])
        self.assertEqual(result["report"]["yaml_checked"], 1)

    def test_repeated_calls_are_stable(self) -> None:
        srv = self._make_server_stub()
        r1 = srv.config_validate_api()
        r2 = srv.config_validate_api()
        self.assertEqual(r1["ok"], r2["ok"])
        self.assertEqual(r1["report"]["files_checked"], r2["report"]["files_checked"])

    def test_nonexistent_root_returns_ok_false(self) -> None:
        """A missing scan root must return ok=False, not a false-clean green report."""
        srv = self._make_server_stub(self.tmp_path / "does_not_exist")
        result = srv.config_validate_api()
        self.assertFalse(result["ok"])
        self.assertEqual(result["report"]["files_checked"], 0)
        self.assertGreater(len(result["report"]["errors"]), 0)

    def test_report_has_yaml_skipped_field(self) -> None:
        """ValidationReport.to_dict() must expose yaml_skipped."""
        srv = self._make_server_stub()
        report = srv.config_validate_api()["report"]
        self.assertIn("yaml_skipped", report)

    def test_invalid_utf8_json_returns_ok_false(self) -> None:
        """Files with invalid UTF-8 must be flagged as broken (errors='strict')."""
        bad_path = self.tmp_path / "corrupt.json"
        # Write valid JSON structure but with an invalid UTF-8 sequence embedded.
        bad_path.write_bytes(b'{"key": "val\xff ue"}')
        srv = self._make_server_stub()
        result = srv.config_validate_api()
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["report"]["errors"]), 1)


# ---------------------------------------------------------------------------
# Route: GET /api/config/validate dispatches to do_GET
# ---------------------------------------------------------------------------

class TestConfigValidateRoute(unittest.TestCase):
    """GET /api/config/validate must be wired in AdminGuiHandler.do_GET."""

    _source: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls._source = (ROOT / "src" / "admin_gui_server.py").read_text(encoding="utf-8")

    def test_route_string_present_in_do_get(self) -> None:
        self.assertIn('"/api/config/validate"', self._source)

    def test_config_validate_api_called_in_do_get(self) -> None:
        self.assertIn("config_validate_api()", self._source)

    def test_config_validator_imported_or_used(self) -> None:
        self.assertIn("ConfigValidator", self._source)


class TestConfigValidateRouteDispatch(unittest.TestCase):
    """do_GET /api/config/validate returns 200 with ok/version/report payload."""

    def _call_route(self, path: str):
        calls = []
        responses = []

        class ServerStub:
            def config_validate_api(self_inner):
                calls.append(1)
                return {
                    "ok": True,
                    "version": RUNTIME_VERSION,
                    "report": {"ok": True, "files_checked": 0, "json_checked": 0,
                               "yaml_checked": 0, "errors": [], "version": RUNTIME_VERSION},
                }

        handler = object.__new__(admin_gui_server.AdminGuiHandler)
        handler.path = path
        handler.server = ServerStub()
        handler._send_json = lambda obj, status=200: responses.append((status, obj))

        admin_gui_server.AdminGuiHandler.do_GET(handler)
        return responses, calls

    def test_route_responds_200(self) -> None:
        responses, calls = self._call_route("/api/config/validate")
        self.assertEqual(len(responses), 1)
        status, payload = responses[0]
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(len(calls), 1)

    def test_route_payload_has_report(self) -> None:
        responses, _ = self._call_route("/api/config/validate")
        _, payload = responses[0]
        self.assertIn("report", payload)

    def test_unknown_path_does_not_call_config_validate(self) -> None:
        responses, calls = self._call_route("/api/other")
        self.assertEqual(len(calls), 0)


if __name__ == "__main__":
    unittest.main()
