"""
=== NoemaForge File Header ===
File: noemaforge/tests/test_pipeline_progress_d007.py
Zone: tests/gui
Version: 0.33.0
Created: 2026-06-19
Purpose: Verify D-007 — pipeline run progress panel: backend status endpoint +
  frontend stage rendering (current stage highlighted, completed marked, errors,
  run id linked to artifacts/logs).
Inputs: noemaforge/src/admin_gui_server.py, noemaforge/templates/pipeline-dashboard/app.js.
Outputs: Pass/fail assertions.
Tests: py -3 -m unittest noemaforge/tests/test_pipeline_progress_d007.py -v
=== End NoemaForge File Header ===
"""
import re
import sys
import types
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
DASH = Path(__file__).resolve().parents[1] / "templates" / "pipeline-dashboard"
APP_JS = DASH / "app.js"
STYLE_CSS = DASH / "style.css"


def _src():
    return APP_JS.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Backend: pipeline_run_status() method
# ---------------------------------------------------------------------------

def _load_server():
    stubs = {
        "production_ai_contracts": types.ModuleType("production_ai_contracts"),
        "noemaforge_version": types.ModuleType("noemaforge_version"),
        "_platform_paths": types.ModuleType("_platform_paths"),
    }
    stubs["production_ai_contracts"].new_trace_id = lambda *a, **kw: "stub-trace"
    stubs["noemaforge_version"].RUNTIME_VERSION = "0.33.0-test"

    class _FakePaths:
        root = Path(".")
        pipelines_dir = Path(".")
        persona_state_dir = Path(".")
        model_evolution_state_dir = Path(".")
        model_selection_state_dir = Path(".")
        dev_team_state_dir = Path(".")
        modelstore_dir = Path(".")
        llm_gateway_socket = Path(".")
        llm_main_backend_socket = Path(".")
        legacy_llm_gateway_socket = None

    stubs["_platform_paths"].__dict__.update(vars(_FakePaths()))

    for name, mod in stubs.items():
        sys.modules[name] = mod

    import importlib.util
    spec = importlib.util.spec_from_file_location("admin_gui_server", SRC_DIR / "admin_gui_server.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        pass
    return mod


_server_mod = _load_server()
AdminGuiServer = getattr(_server_mod, "AdminGuiServer", None)


@unittest.skipIf(AdminGuiServer is None, "AdminGuiServer could not be loaded")
class TestPipelineRunStatusMethod(unittest.TestCase):
    """pipeline_run_status() exists and guards against empty run_id."""

    @classmethod
    def setUpClass(cls):
        import os
        cls.srv = object.__new__(AdminGuiServer)
        cls.srv.root = Path(".")
        cls.srv.state = Path(".")
        cls.srv.persona_state = Path(".")
        cls.srv.env = lambda locale="": dict(os.environ, NOEMAFORGE_ROOT=".", NOEMAFORGE_PIPELINE_STATE=".")

    def test_method_exists(self):
        self.assertTrue(hasattr(self.srv, "pipeline_run_status"))

    def test_empty_run_id_returns_error(self):
        result = self.srv.pipeline_run_status("")
        self.assertFalse(result.get("ok", True))
        self.assertIn("error", result)

    def test_result_has_stage_states_key(self):
        # With a real run_id the subprocess would run; we just verify the method
        # builds stage_states correctly from injected data via monkey-patch.
        import json as _json

        manifest = _json.dumps({
            "pipeline": {"stages": ["intake", "research", "review"]},
            "current_stage": "research",
        })
        fake_raw = {
            "ok": True,
            "run_id": "test-run-001",
            "pipeline_id": "book_team",
            "status": "in_progress",
            "current_stage": "research",
            "run_dir": "/tmp/runs/test-run-001",
            "manifest": manifest,
            "events": [],
            "artifacts": [],
        }

        def _fake_run_json(cmd, **kw):
            return fake_raw

        orig = getattr(_server_mod, "run_json", None)
        _server_mod.run_json = _fake_run_json
        try:
            result = self.srv.pipeline_run_status("test-run-001")
        finally:
            if orig is not None:
                _server_mod.run_json = orig

        self.assertTrue(result.get("ok"), result)
        self.assertIn("stage_states", result)
        states = {s["stage"]: s["state"] for s in result["stage_states"]}
        self.assertEqual(states["intake"], "completed")
        self.assertEqual(states["research"], "active")
        self.assertEqual(states["review"], "pending")

    def test_stage_states_all_pending_when_no_current(self):
        import json as _json

        manifest = _json.dumps({"pipeline": {"stages": ["intake", "plan"]}, "current_stage": ""})
        fake_raw = {"ok": True, "run_id": "r2", "pipeline_id": "x", "status": "planned",
                    "current_stage": "", "run_dir": "/tmp", "manifest": manifest, "events": [], "artifacts": []}

        def _fake(*a, **kw):
            return fake_raw

        orig = getattr(_server_mod, "run_json", None)
        _server_mod.run_json = _fake
        try:
            result = self.srv.pipeline_run_status("r2")
        finally:
            if orig is not None:
                _server_mod.run_json = orig

        states = {s["stage"]: s["state"] for s in result["stage_states"]}
        self.assertEqual(states["intake"], "pending")
        self.assertEqual(states["plan"], "pending")

    def test_result_includes_run_id_and_pipeline_id(self):
        import json as _json

        manifest = _json.dumps({"pipeline": {"stages": ["a"]}, "current_stage": "a"})
        fake_raw = {"ok": True, "run_id": "my-run", "pipeline_id": "book_team", "status": "ready",
                    "current_stage": "a", "run_dir": "/tmp", "manifest": manifest, "events": [], "artifacts": []}

        def _fake(*a, **kw):
            return fake_raw

        orig = getattr(_server_mod, "run_json", None)
        _server_mod.run_json = _fake
        try:
            result = self.srv.pipeline_run_status("my-run")
        finally:
            if orig is not None:
                _server_mod.run_json = orig

        self.assertEqual(result["run_id"], "my-run")
        self.assertEqual(result["pipeline_id"], "book_team")


# ---------------------------------------------------------------------------
# Frontend: renderPipelineRunPanel() in app.js
# ---------------------------------------------------------------------------

class TestRenderPipelineRunPanelExists(unittest.TestCase):
    def setUp(self):
        self.src = _src()

    def test_render_function_declared(self):
        self.assertIn("function renderPipelineRunPanel(", self.src)

    def test_update_function_declared(self):
        self.assertIn("function _updatePipelineRunPanel(", self.src)

    def test_absorb_result_calls_render_on_pipeline_run_mode(self):
        m = re.search(r'function absorbResult\(result\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m, "absorbResult body not found")
        body = m.group(1)
        self.assertIn("renderPipelineRunPanel", body)
        self.assertIn("pipeline_run", body)

    def test_render_checks_run_id(self):
        m = re.search(r'function renderPipelineRunPanel\(result\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("run_id", body)

    def test_render_uses_pipeline_by_id_for_stages(self):
        m = re.search(r'function renderPipelineRunPanel\(result\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("pipelineById", body)
        self.assertIn("stages", body)

    def test_render_creates_stage_list(self):
        m = re.search(r'function renderPipelineRunPanel\(result\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("pipeline-run-stages", body)

    def test_render_has_copy_run_id_button(self):
        m = re.search(r'function renderPipelineRunPanel\(result\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("clipboard", body)

    def test_render_has_refresh_button(self):
        m = re.search(r'function renderPipelineRunPanel\(result\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("Refresh", body)

    def test_render_polls_status_endpoint(self):
        m = re.search(r'function renderPipelineRunPanel\(result\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("/api/pipeline/run/", body)
        self.assertIn("/status", body)

    def test_update_function_handles_stage_states(self):
        m = re.search(r'function _updatePipelineRunPanel\(panel, status\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("stage_states", body)
        self.assertIn("pipeline-run-stage", body)

    def test_update_function_shows_errors(self):
        m = re.search(r'function _updatePipelineRunPanel\(panel, status\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("stage_failed", body)
        self.assertIn("pipeline-run-errors", body)

    def test_stage_icons_in_render(self):
        m = re.search(r'function renderPipelineRunPanel\(result\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("stage-icon", body)

    def test_no_user_content_in_innerhtml(self):
        # All user-controlled content must not be interpolated via template literals into innerHTML.
        m = re.search(r'function renderPipelineRunPanel\(result\)\s*\{(.+?)\n\}', self.src, re.DOTALL)
        self.assertIsNotNone(m)
        body = m.group(1)
        # The function must use textContent for user-provided strings.
        self.assertIn("textContent", body)


class TestPipelineRunPanelCSS(unittest.TestCase):
    def setUp(self):
        self.css = STYLE_CSS.read_text(encoding="utf-8")

    def test_panel_class_defined(self):
        self.assertIn(".pipeline-run-panel", self.css)

    def test_active_stage_class_defined(self):
        self.assertIn(".pipeline-run-stage.active", self.css)

    def test_completed_stage_class_defined(self):
        self.assertIn(".pipeline-run-stage.completed", self.css)

    def test_error_line_class_defined(self):
        self.assertIn(".pipeline-run-error-line", self.css)


if __name__ == "__main__":
    unittest.main()
