#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_noema_doctor.py
Zone: tests/diagnostics
Version: 0.33.0
Created: 2026-06-07
Modified: 2026-06-07
Purpose: Unit tests for noema_doctor (the read-only readiness command).
Inputs: None; uses the in-repo package tree and temp dirs.
Outputs: unittest results.
Side effects: None beyond temp dirs; admin probe disabled in tests.
Tests: python3 -m unittest test_noema_doctor
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
PKG = Path(__file__).resolve().parents[1]  # noemaforge/
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import noema_doctor as nd  # noqa: E402


class NoemaDoctorTests(unittest.TestCase):
    def _report(self, **kw):
        kw.setdefault("probe_admin", False)
        return nd.collect_report(package_root=PKG, **kw)

    def test_report_structure_and_never_raises(self):
        r = self._report()
        for key in ("apiVersion", "kind", "generated_at", "version", "platform", "ok", "summary", "checks"):
            self.assertIn(key, r)
        self.assertEqual(r["apiVersion"], "noemaforge.doctor-report/v1")
        self.assertEqual(r["kind"], "DoctorReport")
        self.assertIsInstance(r["checks"], list)
        self.assertTrue(r["checks"])
        self.assertIsInstance(r["ok"], bool)

    def test_python_runtime_check_ok_on_this_interpreter(self):
        r = self._report()
        py = next(c for c in r["checks"] if c["id"] == "python_runtime")
        # The test interpreter is always >= the minimum (3.10).
        self.assertEqual(py["level"], "ok")

    def test_healthy_tree_has_no_critical(self):
        r = self._report()
        self.assertTrue(r["ok"])
        self.assertEqual(r["summary"]["critical"], 0)

    def test_policies_and_schemas_detected_in_real_package(self):
        r = self._report()
        pol = next(c for c in r["checks"] if c["id"] == "policies")
        sch = next(c for c in r["checks"] if c["id"] == "schemas")
        self.assertEqual(pol["level"], "ok", pol)
        self.assertEqual(sch["level"], "ok", sch)

    def test_missing_package_root_warns_but_does_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            r = nd.collect_report(package_root=Path(d), probe_admin=False)
        pol = next(c for c in r["checks"] if c["id"] == "policies")
        sch = next(c for c in r["checks"] if c["id"] == "schemas")
        self.assertEqual(pol["level"], "warn")
        self.assertEqual(sch["level"], "warn")
        # Missing policy/schema files are warnings, not critical: still "ready".
        self.assertTrue(r["ok"])

    def test_admin_probe_skipped_when_disabled(self):
        r = self._report(probe_admin=False)
        admin = [c for c in r["checks"] if c["id"] == "admin_control_plane"]
        self.assertTrue(admin)
        self.assertIn("skipped", admin[0]["detail"])

    def test_display_safety_reminder_present(self):
        r = self._report()
        ds = next(c for c in r["checks"] if c["id"] == "display_safety")
        self.assertIn("--keep-display", ds["detail"])

    def test_format_human_renders_overall(self):
        text = nd.format_human(self._report())
        self.assertIn("NoemaForge doctor", text)
        self.assertIn("OVERALL: READY", text)

    def test_main_json_exits_zero_and_emits_json(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = nd.main(["--json", "--no-admin-probe", "--package-root", str(PKG)])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["kind"], "DoctorReport")
        self.assertTrue(payload["ok"])

    def test_probe_admin_parses_addresses_without_raising(self):
        # Unparseable / closed addresses must return a dict, never raise.
        self.assertIsInstance(nd._probe_admin("not-an-address"), dict)
        self.assertIsInstance(nd._probe_admin(("127.0.0.1", 1)), dict)
        # A very likely-closed high port resolves to listening False quickly.
        res = nd._probe_admin("127.0.0.1:65000")
        self.assertIn("listening", res)


if __name__ == "__main__":
    unittest.main()
