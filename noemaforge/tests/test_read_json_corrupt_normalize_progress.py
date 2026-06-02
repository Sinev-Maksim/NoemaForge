#!/usr/bin/env python3
"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_read_json_corrupt_normalize_progress.py
Zone: tests
Version: 0.32.2
Created: 2026-06-01
Modified: 2026-06-01
Purpose: Tests for tasks 87-88:
           - task-87 (LOW): _read_json() must emit a stderr warning when it
             catches an exception (e.g. JSONDecodeError from a corrupt file)
             instead of silently returning the default. The warning makes
             operator-visible corruption detectable without disrupting availability.
           - task-88 (LOW): normalize_job_progress() helper in orchestration_state.py
             ensures all three sub-fields (current, total, label) are present in
             the progress dict, even when the stored record supplies only some of
             them. normalize_job_record() now calls normalize_job_progress() so
             the schema guarantee propagates to all callers.
Inputs: admin_gui_server.py source text; orchestration_state module.
Outputs: pytest pass/fail.
Side effects: Writes and removes files under tempfile.mkdtemp(); reads stderr.
Tests: python3 -m unittest noemaforge/tests/test_read_json_corrupt_normalize_progress.py -v
Notes: Code comments are English-only.
=== End NoemaForge File Header ===
"""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _install_stubs() -> None:
    import noemaforge_version as real_version
    sys.modules.setdefault("noemaforge_version", real_version)

    stub_orch = types.ModuleType("orchestration_state")
    stub_orch.nowz = lambda: "2026-06-01T00:00:00Z"
    stub_orch.normalize_session_record = lambda r: r
    stub_orch.normalize_job_record = lambda r: r
    stub_orch.is_active_job = lambda job: False
    stub_orch.ACTIVE_JOB_STATES = {"queued", "starting", "running", "cancel_requested", "needs_privilege"}
    stub_orch.FINAL_JOB_STATES = {"done", "failed", "cancelled"}
    sys.modules.setdefault("orchestration_state", stub_orch)

    stub_prod = types.ModuleType("production_ai_contracts")
    stub_prod.new_trace_id = lambda kind="": f"trace_{kind}"
    sys.modules.setdefault("production_ai_contracts", stub_prod)

    stub_priv = types.ModuleType("privileged_gui_job_runner")
    stub_priv.enrich_privileged_job = lambda job, **_kw: job
    sys.modules.setdefault("privileged_gui_job_runner", stub_priv)


_install_stubs()

_ADMIN_SRC = (_SRC / "admin_gui_server.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Source-guard helpers
# ---------------------------------------------------------------------------

def _read_json_body() -> str:
    start = _ADMIN_SRC.index("def _read_json(self")
    end = _ADMIN_SRC.index("\n    def ", start + 1)
    return _ADMIN_SRC[start:end]


# ---------------------------------------------------------------------------
# task-87: _read_json() must write stderr warning on exception
# ---------------------------------------------------------------------------

class TestReadJsonCorruptWarning(unittest.TestCase):
    """task-87: _read_json() must log to stderr when an exception is caught."""

    def test_stderr_write_in_except_block(self) -> None:
        """except block in _read_json must call stderr.write (or equivalent)."""
        body = _read_json_body()
        self.assertIn("stderr", body,
                      "_read_json() except block must write a warning to stderr")

    def test_except_includes_path_in_message(self) -> None:
        """The stderr warning must reference the file path."""
        body = _read_json_body()
        self.assertIn("path", body,
                      "_read_json() warning must include the file path for operator diagnosis")

    def test_exception_captured_in_except_clause(self) -> None:
        """except clause must capture the exception (except Exception as exc)."""
        body = _read_json_body()
        self.assertIn("except Exception as exc", body,
                      "_read_json() must capture the exception with 'as exc' for logging")

    def test_still_returns_default_on_exception(self) -> None:
        """_read_json() must return default after logging, not re-raise."""
        body = _read_json_body()
        # 'return default' must appear after the stderr.write
        stderr_idx = body.index("stderr")
        return_idx = body.index("return default", stderr_idx)
        self.assertLess(stderr_idx, return_idx,
                        "_read_json() must return default after writing to stderr")


class TestReadJsonCorruptBehavioural(unittest.TestCase):
    """Behavioural: _read_json() must warn on stderr and return default for corrupt JSON."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_corrupt_json_returns_default_and_writes_stderr(self) -> None:
        """_read_json on a corrupt file must return default and write a stderr warning."""
        from admin_gui_server import AdminGuiServer
        srv = object.__new__(AdminGuiServer)
        corrupt_file = Path(self._tmpdir) / "corrupt.json"
        corrupt_file.write_text("{ not valid json !!!", encoding="utf-8")
        stderr_capture = io.StringIO()
        old_stderr = sys.stderr
        try:
            sys.stderr = stderr_capture
            result = AdminGuiServer._read_json(srv, corrupt_file, {"default": True})
        finally:
            sys.stderr = old_stderr
        self.assertEqual(result, {"default": True},
                         "_read_json must return default for corrupt JSON")
        warning = stderr_capture.getvalue()
        self.assertIn("_read_json", warning,
                      "stderr must contain '_read_json' in the warning message")
        self.assertIn("corrupt.json", warning,
                      "stderr must name the corrupt file in the warning")

    def test_valid_json_returns_data_no_stderr(self) -> None:
        """_read_json on a valid file must return parsed data with no stderr output."""
        from admin_gui_server import AdminGuiServer
        srv = object.__new__(AdminGuiServer)
        valid_file = Path(self._tmpdir) / "valid.json"
        valid_file.write_text('{"key": "value"}', encoding="utf-8")
        stderr_capture = io.StringIO()
        old_stderr = sys.stderr
        try:
            sys.stderr = stderr_capture
            result = AdminGuiServer._read_json(srv, valid_file, {})
        finally:
            sys.stderr = old_stderr
        self.assertEqual(result, {"key": "value"})
        self.assertEqual(stderr_capture.getvalue(), "",
                         "No stderr output expected for valid JSON")

    def test_missing_file_returns_default_no_stderr(self) -> None:
        """_read_json on a non-existent file must return default with no stderr output."""
        from admin_gui_server import AdminGuiServer
        srv = object.__new__(AdminGuiServer)
        missing = Path(self._tmpdir) / "does_not_exist.json"
        stderr_capture = io.StringIO()
        old_stderr = sys.stderr
        try:
            sys.stderr = stderr_capture
            result = AdminGuiServer._read_json(srv, missing, "fallback")
        finally:
            sys.stderr = old_stderr
        self.assertEqual(result, "fallback")
        self.assertEqual(stderr_capture.getvalue(), "",
                         "No stderr output expected for missing file (not an error)")


# ---------------------------------------------------------------------------
# task-88: normalize_job_progress() helper in orchestration_state
# ---------------------------------------------------------------------------

class TestNormalizeJobProgress(unittest.TestCase):
    """task-88: normalize_job_progress() must guarantee all sub-fields present."""

    def setUp(self) -> None:
        import noemaforge_version as real_version
        sys.modules["noemaforge_version"] = real_version

    def _get_normalize_job_progress(self):
        # Import real orchestration_state (not stub)
        import importlib
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "orchestration_state_real", _SRC / "orchestration_state.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.normalize_job_progress

    def test_none_progress_gets_defaults(self) -> None:
        """None progress must become {'current':0,'total':0,'label':'queued'}."""
        normalize_job_progress = self._get_normalize_job_progress()
        result = normalize_job_progress(None)
        self.assertEqual(result, {"current": 0, "total": 0, "label": "queued"})

    def test_non_dict_progress_gets_defaults(self) -> None:
        """Non-dict progress (e.g. a string) must become the default dict."""
        normalize_job_progress = self._get_normalize_job_progress()
        result = normalize_job_progress("50%")
        self.assertEqual(result, {"current": 0, "total": 0, "label": "queued"})

    def test_complete_dict_preserved(self) -> None:
        """A dict with all three keys must have its values preserved."""
        normalize_job_progress = self._get_normalize_job_progress()
        p = {"current": 5, "total": 10, "label": "running"}
        result = normalize_job_progress(p)
        self.assertEqual(result["current"], 5)
        self.assertEqual(result["total"], 10)
        self.assertEqual(result["label"], "running")

    def test_partial_dict_fills_missing_keys(self) -> None:
        """A dict with only 'current' must have 'total' and 'label' filled."""
        normalize_job_progress = self._get_normalize_job_progress()
        result = normalize_job_progress({"current": 3})
        self.assertEqual(result["current"], 3)
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["label"], "queued")

    def test_empty_dict_gets_all_defaults(self) -> None:
        """An empty dict must get all three defaults."""
        normalize_job_progress = self._get_normalize_job_progress()
        result = normalize_job_progress({})
        self.assertEqual(result, {"current": 0, "total": 0, "label": "queued"})

    def test_non_int_current_converted(self) -> None:
        """Non-integer 'current' must be safely converted to int."""
        normalize_job_progress = self._get_normalize_job_progress()
        result = normalize_job_progress({"current": "7", "total": 10, "label": "ok"})
        self.assertEqual(result["current"], 7)

    def test_non_numeric_current_defaults_to_zero(self) -> None:
        """Non-numeric 'current' (e.g. 'abc') must default to 0."""
        normalize_job_progress = self._get_normalize_job_progress()
        result = normalize_job_progress({"current": "abc", "total": 10, "label": "ok"})
        self.assertEqual(result["current"], 0)

    def test_normalize_job_record_uses_normalize_progress(self) -> None:
        """normalize_job_record must normalize progress sub-fields via normalize_job_progress."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "orchestration_state_real2", _SRC / "orchestration_state.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # Progress dict missing 'label' — should be filled to "queued"
        record = {"job_id": "j1", "status": "running", "progress": {"current": 3, "total": 5}}
        result = mod.normalize_job_record(record)
        self.assertEqual(result["progress"]["label"], "queued",
                         "Missing 'label' in progress dict must default to 'queued'")
        self.assertEqual(result["progress"]["current"], 3)
        self.assertEqual(result["progress"]["total"], 5)


class TestNormalizeJobProgressSourceGuard(unittest.TestCase):
    """Source-guard: normalize_job_progress must be defined in orchestration_state.py."""

    def test_normalize_job_progress_defined(self) -> None:
        """orchestration_state.py must define normalize_job_progress()."""
        src = (_SRC / "orchestration_state.py").read_text(encoding="utf-8")
        self.assertIn("def normalize_job_progress(", src,
                      "orchestration_state.py must define normalize_job_progress()")

    def test_normalize_job_record_calls_normalize_job_progress(self) -> None:
        """normalize_job_record() must call normalize_job_progress()."""
        src = (_SRC / "orchestration_state.py").read_text(encoding="utf-8")
        rec_start = src.index("def normalize_job_record(")
        rec_end = src.index("\n\n\n", rec_start)
        body = src[rec_start:rec_end]
        self.assertIn("normalize_job_progress(", body,
                      "normalize_job_record() must call normalize_job_progress()")


if __name__ == "__main__":
    unittest.main()
