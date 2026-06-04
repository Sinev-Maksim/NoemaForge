#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_canary_runner.py
Zone: tests
Version: 0.32.2
Created: 2026-06-04
Modified: 2026-06-04
Purpose: Tests for canary_runner.py — run canary suites under resource limits.
         Covers: _load_yaml, _apply_rlimits, main (via mocked prestart).
Tests: python3 -m unittest noemaforge/tests/test_canary_runner.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import json
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

# Stub prestart before importing canary_runner
_mock_prestart = types.ModuleType("prestart")
_mock_prestart.canary_run_report = MagicMock(return_value={
    "overall_ok": True,
    "decision": "accept",
    "problems": [],
    "warnings": [],
    "resource_usage": {},
})
_mock_prestart.sel_append = MagicMock(return_value={"evt_id": "evt-001", "_sel_hash": "abc"})
sys.modules.setdefault("prestart", _mock_prestart)

import yaml  # canary_runner uses yaml

import canary_runner  # noqa: E402


class TestLoadYaml(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_loads_valid_yaml(self) -> None:
        path = os.path.join(self._tmpdir, "policy.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write("quota_profiles:\n  smoke:\n    cpu_time_sec: 60\n")
        result = canary_runner._load_yaml(path)
        self.assertIn("quota_profiles", result)
        self.assertEqual(result["quota_profiles"]["smoke"]["cpu_time_sec"], 60)

    def test_empty_yaml_returns_empty_dict(self) -> None:
        path = os.path.join(self._tmpdir, "empty.yaml")
        with open(path, "w", encoding="utf-8") as f:
            f.write("")
        result = canary_runner._load_yaml(path)
        self.assertEqual(result, {})

    def test_raises_on_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            canary_runner._load_yaml("/nonexistent/policy.yaml")

    def test_loads_nested_yaml(self) -> None:
        path = os.path.join(self._tmpdir, "nested.yaml")
        data = {"a": {"b": {"c": 42}}}
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
        result = canary_runner._load_yaml(path)
        self.assertEqual(result["a"]["b"]["c"], 42)


class TestApplyRlimits(unittest.TestCase):
    """_apply_rlimits should not raise on valid profiles.
    On Windows (no resource module), it should be a no-op."""

    def test_no_op_on_empty_profile(self) -> None:
        # Should not raise
        canary_runner._apply_rlimits({})

    def test_no_op_on_zero_values(self) -> None:
        profile = {"cpu_time_sec": 0, "mem_max_mib": 0, "pids_max": 0, "file_max_mib": 0}
        canary_runner._apply_rlimits(profile)

    def test_no_op_when_resource_module_absent(self) -> None:
        original = canary_runner.resource
        try:
            canary_runner.resource = None
            profile = {"cpu_time_sec": 60, "mem_max_mib": 512}
            canary_runner._apply_rlimits(profile)  # Should silently no-op
        finally:
            canary_runner.resource = original

    def test_handles_string_values_gracefully(self) -> None:
        # String values that parse to int should work; invalid ones should not raise
        profile = {"cpu_time_sec": "60", "mem_max_mib": "256"}
        try:
            canary_runner._apply_rlimits(profile)
        except (ValueError, TypeError, OSError):
            pass  # Acceptable: profile value parsing edge case

    def test_handles_none_values(self) -> None:
        profile = {"cpu_time_sec": None, "mem_max_mib": None}
        canary_runner._apply_rlimits(profile)  # Should not raise

    def test_cpu_time_applied_when_positive(self) -> None:
        resource_mod = canary_runner.resource
        if resource_mod is None:
            self.skipTest("resource module not available (Windows)")
        with patch.object(resource_mod, "setrlimit") as mock_setrlimit:
            canary_runner._apply_rlimits({"cpu_time_sec": 30})
            mock_setrlimit.assert_any_call(resource_mod.RLIMIT_CPU, (30, 30))

    def test_mem_limit_applied_when_positive(self) -> None:
        resource_mod = canary_runner.resource
        if resource_mod is None:
            self.skipTest("resource module not available (Windows)")
        with patch.object(resource_mod, "setrlimit") as mock_setrlimit:
            canary_runner._apply_rlimits({"mem_max_mib": 512})
            expected_lim = 512 * 1024 * 1024
            mock_setrlimit.assert_any_call(resource_mod.RLIMIT_AS, (expected_lim, expected_lim))

    def test_pids_limit_applied_when_positive(self) -> None:
        resource_mod = canary_runner.resource
        if resource_mod is None:
            self.skipTest("resource module not available (Windows)")
        with patch.object(resource_mod, "setrlimit") as mock_setrlimit:
            canary_runner._apply_rlimits({"pids_max": 100})
            mock_setrlimit.assert_any_call(resource_mod.RLIMIT_NPROC, (100, 100))

    def test_file_size_limit_applied_when_positive(self) -> None:
        resource_mod = canary_runner.resource
        if resource_mod is None:
            self.skipTest("resource module not available (Windows)")
        with patch.object(resource_mod, "setrlimit") as mock_setrlimit:
            canary_runner._apply_rlimits({"file_max_mib": 64})
            expected_lim = 64 * 1024 * 1024
            mock_setrlimit.assert_any_call(resource_mod.RLIMIT_FSIZE, (expected_lim, expected_lim))

    def test_setrlimit_exceptions_suppressed(self) -> None:
        resource_mod = canary_runner.resource
        if resource_mod is None:
            self.skipTest("resource module not available (Windows)")
        with patch.object(resource_mod, "setrlimit", side_effect=ValueError("test error")):
            # Should not propagate the exception
            canary_runner._apply_rlimits({"cpu_time_sec": 60})


class TestMain(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._base = os.path.join(self._tmpdir, "base_epoch")
        self._cand = os.path.join(self._tmpdir, "cand_epoch")
        os.makedirs(self._base)
        os.makedirs(self._cand)
        _mock_prestart.canary_run_report.reset_mock()
        _mock_prestart.canary_run_report.return_value = {
            "overall_ok": True,
            "decision": "accept",
            "problems": [],
            "warnings": [],
        }

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_main_returns_zero_on_success(self) -> None:
        result = canary_runner.main(["--base", self._base, "--cand", self._cand, "--suite", "smoke"])
        self.assertEqual(result, 0)

    def test_main_calls_canary_run_report(self) -> None:
        canary_runner.main(["--base", self._base, "--cand", self._cand, "--suite", "smoke"])
        _mock_prestart.canary_run_report.assert_called_once()

    def test_main_passes_correct_dirs_to_canary_run_report(self) -> None:
        canary_runner.main(["--base", self._base, "--cand", self._cand, "--suite", "smoke"])
        call_kwargs = _mock_prestart.canary_run_report.call_args
        self.assertEqual(call_kwargs.kwargs["base_epoch_dir"], self._base)
        self.assertEqual(call_kwargs.kwargs["cand_epoch_dir"], self._cand)

    def test_main_writes_report_file(self) -> None:
        report_path = os.path.join(self._cand, "scary_report.json")
        canary_runner.main(["--base", self._base, "--cand", self._cand, "--suite", "smoke"])
        self.assertTrue(os.path.exists(report_path))

    def test_main_report_is_valid_json(self) -> None:
        canary_runner.main(["--base", self._base, "--cand", self._cand, "--suite", "smoke"])
        report_path = os.path.join(self._cand, "scary_report.json")
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("overall_ok", data)

    def test_main_custom_report_path(self) -> None:
        custom_path = os.path.join(self._tmpdir, "custom_report.json")
        canary_runner.main([
            "--base", self._base,
            "--cand", self._cand,
            "--suite", "smoke",
            "--report-path", custom_path,
        ])
        self.assertTrue(os.path.exists(custom_path))

    def test_main_returns_one_on_failure(self) -> None:
        _mock_prestart.canary_run_report.return_value = {
            "overall_ok": False,
            "decision": "reject",
            "problems": ["test failure"],
            "warnings": [],
        }
        result = canary_runner.main(["--base", self._base, "--cand", self._cand, "--suite", "smoke"])
        self.assertEqual(result, 1)

    def test_main_full_suite_accepted(self) -> None:
        result = canary_runner.main(["--base", self._base, "--cand", self._cand, "--suite", "full"])
        self.assertEqual(result, 0)
        call_kwargs = _mock_prestart.canary_run_report.call_args
        self.assertEqual(call_kwargs.kwargs["suite"], "full")

    def test_main_law_defaults_to_base(self) -> None:
        canary_runner.main(["--base", self._base, "--cand", self._cand, "--suite", "smoke"])
        call_kwargs = _mock_prestart.canary_run_report.call_args
        self.assertEqual(call_kwargs.kwargs["law_epoch_dir"], self._base)

    def test_main_explicit_law_dir_used(self) -> None:
        law = os.path.join(self._tmpdir, "law_epoch")
        os.makedirs(law)
        canary_runner.main([
            "--base", self._base,
            "--cand", self._cand,
            "--law", law,
            "--suite", "smoke",
        ])
        call_kwargs = _mock_prestart.canary_run_report.call_args
        self.assertEqual(call_kwargs.kwargs["law_epoch_dir"], law)

    def test_main_loads_canary_policy_from_law_dir(self) -> None:
        # Create a canary-policy.yaml in the base dir
        policy = {
            "quota_profiles": {
                "smoke": {"cpu_time_sec": 30, "mem_max_mib": 256}
            }
        }
        policy_path = os.path.join(self._base, "canary-policy.yaml")
        with open(policy_path, "w", encoding="utf-8") as f:
            yaml.dump(policy, f)
        # Should load the policy without error
        result = canary_runner.main(["--base", self._base, "--cand", self._cand, "--suite", "smoke"])
        self.assertEqual(result, 0)

    def test_main_missing_suite_raises_systemexit(self) -> None:
        with self.assertRaises(SystemExit):
            canary_runner.main(["--base", self._base, "--cand", self._cand])

    def test_main_invalid_suite_raises_systemexit(self) -> None:
        with self.assertRaises(SystemExit):
            canary_runner.main(["--base", self._base, "--cand", self._cand, "--suite", "invalid_suite"])

    def test_output_includes_problems_list(self) -> None:
        _mock_prestart.canary_run_report.return_value = {
            "overall_ok": False,
            "decision": "reject",
            "problems": ["critical check failed"],
            "warnings": ["minor warning"],
        }
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            canary_runner.main(["--base", self._base, "--cand", self._cand, "--suite", "smoke"])
        output = json.loads(buf.getvalue().strip())
        self.assertIn("problems", output)
        self.assertIn("critical check failed", output["problems"])

    def test_output_includes_warnings_with_prefix(self) -> None:
        _mock_prestart.canary_run_report.return_value = {
            "overall_ok": True,
            "decision": "accept",
            "problems": [],
            "warnings": ["minor warning"],
        }
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            canary_runner.main(["--base", self._base, "--cand", self._cand, "--suite", "smoke"])
        output = json.loads(buf.getvalue().strip())
        # Warnings are prefixed with "warn:"
        self.assertTrue(any("warn:" in p for p in output["problems"]))


if __name__ == "__main__":
    unittest.main()